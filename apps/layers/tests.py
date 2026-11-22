import json
from datetime import timedelta
from io import StringIO
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import LayerInfo, LayerShare, LayerShareLink, LayerShareLinkUsage
from .tile_auth import authorize_tile_request, check_share_link, validate_tile_request

SECRET = "test-geolayers-secret"
TABLE = "layer_" + "a" * 32


@override_settings(TILE_AUTH_SHARED_SECRET=SECRET, MARTIN_LAYER_FUNCTION="geolayers_tile")
class TileAuthTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.owner = users.create_user("owner", "owner@example.com", "pw-12345!")
        self.viewer = users.create_user("viewer", "viewer@example.com", "pw-12345!")
        self.stranger = users.create_user("stranger", "stranger@example.com", "pw-12345!")
        self.layer = LayerInfo.objects.create(
            owner=self.owner, name="Roads", schema_name="layers_data", table_name=TABLE
        )
        LayerShare.objects.create(layer=self.layer, shared_with=self.viewer, shared_by=self.owner)
        self.factory = RequestFactory()

    def _request(self, user=None, **headers):
        request = self.factory.get("/tiles-auth/validate/", **headers)
        from django.contrib.auth.models import AnonymousUser

        request.user = user or AnonymousUser()
        return request

    def _decide(self, uri, user=None, **headers):
        return authorize_tile_request(self._request(user, **headers), uri)

    def _link(self, **kwargs):
        kwargs.setdefault("expires_at", timezone.now() + timedelta(days=1))
        return LayerShareLink.objects.create(layer=self.layer, created_by=self.owner, **kwargs)

    # ------------------------------------------------------------ map builder tiles
    def test_owner_and_shared_user_allowed_with_validated_table(self):
        for user in (self.owner, self.viewer):
            decision = self._decide(f"/tiles/geolayers_tile/3/4/5?layer={TABLE}", user)
            self.assertEqual(decision.status, 204)
            self.assertEqual(decision.layer_table, TABLE)

    def test_anonymous_needs_sign_in(self):
        self.assertEqual(self._decide(f"/tiles/geolayers_tile/3/4/5?layer={TABLE}").status, 401)

    def test_unshared_user_is_refused(self):
        self.assertEqual(self._decide(f"/tiles/geolayers_tile/3/4/5?layer={TABLE}", self.stranger).status, 403)

    def test_unknown_or_malformed_layer_is_refused(self):
        self.assertEqual(
            self._decide("/tiles/geolayers_tile/3/4/5?layer=layer_" + "b" * 32, self.owner).status, 403
        )
        self.assertEqual(self._decide("/tiles/geolayers_tile/3/4/5?layer=pg_shadow", self.owner).status, 403)
        self.assertEqual(self._decide("/tiles/riyadh_roads/3/4/5", self.owner).status, 403)

    def test_bearer_jwt_is_accepted(self):
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken.for_user(self.viewer)
        decision = self._decide(
            f"/tiles/geolayers_tile/3/4/5?layer={TABLE}", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(decision.status, 204)

    # ------------------------------------------------------------ share links
    def test_share_link_allows_anyone_and_returns_its_table(self):
        link = self._link()
        decision = self._decide(f"/x/{link.token}/3/4/5.pbf")
        self.assertEqual(decision.status, 204)
        self.assertEqual(decision.layer_table, TABLE)
        self.assertNotIn(link.token, decision.token_label)

    def test_share_link_refusals_carry_reason(self):
        expired = self._link(expires_at=timezone.now() - timedelta(minutes=1))
        blocked = self._link(is_blocked=True)
        cases = {
            "/x/does-not-exist/3/4/5.pbf": "not_found",
            f"/x/{expired.token}/3/4/5.pbf": "expired",
            f"/x/{blocked.token}/3/4/5.pbf": "blocked",
        }
        for uri, reason in cases.items():
            decision = self._decide(uri)
            self.assertEqual((decision.status, decision.reason), (403, reason), uri)

    def test_revoked_link_stops_on_next_tile(self):
        link = self._link()
        uri = f"/x/{link.token}/3/4/5.pbf"
        self.assertEqual(self._decide(uri).status, 204)
        link.delete()
        self.assertEqual(self._decide(uri).reason, "not_found")

    @skipUnless(connection.vendor == "postgresql", "usage upsert uses PostgreSQL ON CONFLICT")
    def test_share_link_usage_is_counted(self):
        link = self._link()
        for _ in range(3):
            self._decide(f"/x/{link.token}/3/4/5.pbf")
        self.assertEqual(LayerShareLinkUsage.objects.get(link=link).request_count, 3)
        link.refresh_from_db()
        self.assertIsNotNone(link.last_used_at)

    # ------------------------------------------------------------ view
    def test_view_requires_shared_secret_and_sets_headers(self):
        link = self._link()
        bad = validate_tile_request(
            self._request(HTTP_X_ORIGINAL_URI=f"/x/{link.token}/1/1/1.pbf", HTTP_X_TILE_AUTH_SECRET="nope")
        )
        self.assertEqual(bad.status_code, 403)

        ok = validate_tile_request(
            self._request(HTTP_X_ORIGINAL_URI=f"/x/{link.token}/1/1/1.pbf", HTTP_X_TILE_AUTH_SECRET=SECRET)
        )
        self.assertEqual(ok.status_code, 204)
        self.assertEqual(ok["X-Tile-Layer"], TABLE)

        denied = validate_tile_request(
            self._request(HTTP_X_ORIGINAL_URI="/x/missing/1/1/1.pbf", HTTP_X_TILE_AUTH_SECRET=SECRET)
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied["X-Tile-Deny-Reason"], "not_found")


# ---------------------------------------------------------------------------------------------
# API, serializer and fallback-proxy tests
# ---------------------------------------------------------------------------------------------
@override_settings(TILES_PUBLIC_URL="/tiles", MARTIN_LAYER_FUNCTION="geolayers_tile")
class ShareLinkApiTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.owner = users.create_user("owner", "owner@example.com", "pw-12345!")
        self.viewer = users.create_user("viewer", "viewer@example.com", "pw-12345!")
        self.layer = LayerInfo.objects.create(
            owner=self.owner, name="Roads", schema_name="layers_data", table_name=TABLE
        )
        LayerShare.objects.create(layer=self.layer, shared_with=self.viewer, shared_by=self.owner)
        self.api = APIClient()

    def _links_url(self):
        return f"/api/layers/{self.layer.id}/share-links/"

    def test_owner_creates_link_with_auto_token_and_absolute_url(self):
        self.api.force_authenticate(self.owner)
        res = self.api.post(
            self._links_url(), {"expires_at": (timezone.now() + timedelta(days=3)).isoformat()}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertGreaterEqual(len(body["token"]), 24)
        self.assertEqual(body["style_url"], f"http://testserver/x/{body['token']}/style.json")
        self.assertEqual(body["xyz_url"], f"http://testserver/x/{body['token']}/{{z}}/{{x}}/{{y}}.pbf")
        self.assertEqual(body["total_requests"], 0)
        self.assertIsNone(body["last_used_at"])
        self.assertFalse(body["never_expires"])
        self.assertNotIn("source_layer", body)
        self.assertNotIn("suggested_geometry", body)

    def test_owner_can_create_link_with_no_expiry(self):
        self.api.force_authenticate(self.owner)
        res = self.api.post(self._links_url(), {"expires_at": None}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertTrue(body["never_expires"])
        self.assertIsNone(body["expires_at"])
        self.assertFalse(body["is_expired"])

    def test_past_expiry_is_rejected(self):
        self.api.force_authenticate(self.owner)
        res = self.api.post(
            self._links_url(), {"expires_at": (timezone.now() - timedelta(days=1)).isoformat()}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_shared_user_cannot_manage_links(self):
        self.api.force_authenticate(self.viewer)
        self.assertEqual(self.api.get(self._links_url()).status_code, 403)

    def test_list_reports_usage_and_revoke_deletes(self):
        link = LayerShareLink.objects.create(
            layer=self.layer, created_by=self.owner, expires_at=timezone.now() + timedelta(days=1)
        )
        LayerShareLinkUsage.objects.create(
            link=link, date=timezone.localdate(), request_count=7, last_request_at=timezone.now()
        )
        LayerShareLinkUsage.objects.create(
            link=link,
            date=timezone.localdate() - timedelta(days=40),
            request_count=5,
            last_request_at=timezone.now() - timedelta(days=40),
        )
        self.api.force_authenticate(self.owner)
        listed = self.api.get(self._links_url()).json()
        self.assertEqual(listed[0]["total_requests"], 12)
        self.assertNotIn("requests_last_30_days", listed[0])

        res = self.api.delete(f"{self._links_url()}{link.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(LayerShareLink.objects.filter(pk=link.pk).exists())

    def test_layer_xyz_url_uses_function_source_and_is_absolute(self):
        self.api.force_authenticate(self.viewer)
        body = self.api.get(f"/api/layers/{self.layer.id}/").json()
        self.assertEqual(
            body["xyz_url"], f"http://testserver/tiles/geolayers_tile/{{z}}/{{x}}/{{y}}?layer={TABLE}"
        )
        self.assertEqual(body["source_layer"], TABLE)

    def test_preview_style_uses_draft_paint_not_saved_style(self):
        self.layer.geometry_type = LayerInfo.GeometryType.LINESTRING
        self.layer.style = {"color": "#ff0000", "strokeWidth": 2, "opacity": 0.9}
        self.layer.label_config = {"field": "name", "size": 14, "color": "#111111"}
        self.layer.save(update_fields=["geometry_type", "style", "label_config"])

        self.api.force_authenticate(self.owner)
        res = self.api.post(
            f"/api/layers/{self.layer.id}/preview-style/",
            {
                "style": {"color": "#00ff00", "strokeWidth": 4, "opacity": 0.5},
                "label_config": {},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(
            body["xyz_url"],
            f"http://testserver/tiles/geolayers_tile/{{z}}/{{x}}/{{y}}?layer={TABLE}",
        )
        self.assertEqual(body["source_id"], f"preview-src-{self.layer.id}")
        line = next(
            layer
            for layer in body["style_layers"]
            if layer["type"] == "line" and "label" not in layer["id"]
        )
        self.assertEqual(line["source-layer"], TABLE)
        self.assertEqual(line["paint"]["line-color"], "#00ff00")
        self.assertFalse(any(layer["type"] == "symbol" for layer in body["style_layers"]))
        self.assertNotIn("glyphs", body)
        self.assertNotIn("geometry_type", body)
        self.assertNotIn("source_layer", body)


@override_settings(MARTIN_INTERNAL_URL="http://martin.test:3000", MARTIN_LAYER_FUNCTION="geolayers_tile")
class ShareTileFallbackProxyTests(TestCase):
    """The Django /x/<token>/ view (used only when running without Nginx)."""

    def setUp(self):
        owner = get_user_model().objects.create_user("owner", "owner@example.com", "pw-12345!")
        self.layer = LayerInfo.objects.create(owner=owner, name="R", schema_name="layers_data", table_name=TABLE)
        self.link = LayerShareLink.objects.create(
            layer=self.layer, created_by=owner, expires_at=timezone.now() + timedelta(days=1)
        )

    @patch("apps.layers.tile_proxy.urllib.request.urlopen")
    def test_valid_link_proxies_to_function_source(self, urlopen):
        upstream = MagicMock(status=200, headers={"Content-Type": "application/x-protobuf"})
        upstream.read.return_value = b"\x1a\x02mvt"
        urlopen.return_value.__enter__.return_value = upstream

        res = self.client.get(f"/x/{self.link.token}/14/10/20.pbf")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, b"\x1a\x02mvt")
        self.assertEqual(res["Access-Control-Allow-Origin"], "*")
        requested = urlopen.call_args[0][0].full_url
        self.assertEqual(requested, f"http://martin.test:3000/geolayers_tile/14/10/20?layer={TABLE}")

    def test_unknown_expired_and_blocked_links(self):
        self.assertEqual(self.client.get("/x/nope/1/1/1.pbf").status_code, 404)
        LayerShareLink.objects.filter(pk=self.link.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"/x/{self.link.token}/1/1/1.pbf").status_code, 410)
        LayerShareLink.objects.filter(pk=self.link.pk).update(
            expires_at=timezone.now() + timedelta(days=1), is_blocked=True
        )
        self.assertEqual(self.client.get(f"/x/{self.link.token}/1/1/1.pbf").status_code, 403)


class ShareStyleDocumentTests(TestCase):
    """Public ``/x/<token>/style.json`` mirrors GeoLayers paint for the same share token."""

    def setUp(self):
        owner = get_user_model().objects.create_user("owner", "owner@example.com", "pw-12345!")
        self.layer = LayerInfo.objects.create(
            owner=owner,
            name="Styled roads",
            schema_name="layers_data",
            table_name=TABLE,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            style={"color": "#ff0000", "strokeWidth": 3, "opacity": 0.9},
            label_config={"field": "name", "size": 14, "color": "#111111"},
            attribute_schema=[{"name": "name", "type": "text"}, {"name": "ref", "type": "text"}],
        )
        self.link = LayerShareLink.objects.create(
            layer=self.layer, created_by=owner, expires_at=timezone.now() + timedelta(days=1)
        )

    def test_style_json_matches_layer_and_points_at_share_tiles(self):
        res = self.client.get(f"/x/{self.link.token}/style.json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Access-Control-Allow-Origin"], "*")
        self.assertIn("application/json", res["Content-Type"])

        body = res.json()
        self.assertEqual(body["version"], 8)
        self.assertEqual(body["name"], "Styled roads")
        self.assertEqual(
            body["sources"]["geolayers"]["tiles"],
            [f"http://testserver/x/{self.link.token}/{{z}}/{{x}}/{{y}}.pbf"],
        )
        self.assertEqual(body["metadata"]["geolayers:source_layer"], TABLE)
        self.assertEqual(body["metadata"]["geolayers:geometry_type"], "LineString")
        self.assertEqual(body["metadata"]["geolayers:style"]["color"], "#ff0000")
        self.assertEqual(
            body["metadata"]["geolayers:attribute_schema"],
            [{"name": "name", "type": "text"}, {"name": "ref", "type": "text"}],
        )

        line = next(layer for layer in body["layers"] if layer["type"] == "line" and "label" not in layer["id"])
        self.assertEqual(line["source-layer"], TABLE)
        self.assertEqual(line["paint"]["line-color"], "#ff0000")
        self.assertEqual(line["paint"]["line-width"][0], "interpolate")

        label = next(layer for layer in body["layers"] if layer["type"] == "symbol")
        self.assertEqual(label["layout"]["text-field"], ["get", "name"])
        self.assertIn("glyphs", body)

    def test_style_json_respects_share_link_lifecycle(self):
        self.assertEqual(self.client.get("/x/nope/style.json").status_code, 404)
        LayerShareLink.objects.filter(pk=self.link.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"/x/{self.link.token}/style.json").status_code, 410)
        LayerShareLink.objects.filter(pk=self.link.pk).update(
            expires_at=timezone.now() + timedelta(days=1), is_blocked=True
        )
        self.assertEqual(self.client.get(f"/x/{self.link.token}/style.json").status_code, 403)


class CategoricalStylePaintTests(TestCase):
    """colorBy / marker.iconBy become MapLibre match expressions for shares + builder."""

    def test_line_color_by_attribute(self):
        from apps.layers.share_style import build_layer_paint_layers

        owner = get_user_model().objects.create_user("cby", "cby@example.com", "pw-12345!")
        layer = LayerInfo.objects.create(
            owner=owner,
            name="Routes",
            schema_name="layers_data",
            table_name="layer_" + "c" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            style={
                "color": "#888888",
                "strokeWidth": 3,
                "opacity": 1,
                "colorBy": {
                    "field": "safety",
                    "default": "#888888",
                    "categories": {"danger": "#dc2626", "safe": "#16a34a"},
                },
            },
            attribute_schema=[{"name": "safety", "type": "text"}],
        )
        layers, _glyphs, icons = build_layer_paint_layers(layer=layer, source_id="s")
        self.assertEqual(icons, [])
        paint = layers[0]["paint"]["line-color"]
        self.assertEqual(paint[0], "match")
        self.assertEqual(paint[1], ["to-string", ["get", "safety"]])
        self.assertIn("danger", paint)
        self.assertIn("#dc2626", paint)
        self.assertEqual(paint[-1], "#888888")

    def test_point_icons_and_color_by(self):
        from apps.layers.share_style import build_layer_paint_layers

        owner = get_user_model().objects.create_user("ico", "ico@example.com", "pw-12345!")
        layer = LayerInfo.objects.create(
            owner=owner,
            name="Stations",
            schema_name="layers_data",
            table_name="layer_" + "d" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            style={
                "color": "#0F2D53",
                "opacity": 0.9,
                "colorBy": {
                    "field": "station_type",
                    "default": "#0F2D53",
                    "categories": {"underground": "#2563eb", "surface": "#16a34a"},
                },
                "marker": {
                    "type": "icon",
                    "icon": "gl-station",
                    "iconBy": {
                        "field": "station_type",
                        "default": "gl-station",
                        "categories": {
                            "underground": "gl-underground",
                            "surface": "gl-station",
                        },
                    },
                },
            },
            attribute_schema=[{"name": "station_type", "type": "text"}],
        )
        layers, needs_glyphs, icons = build_layer_paint_layers(layer=layer, source_id="s")
        symbol = next(
            item
            for item in layers
            if item["type"] == "symbol" and "icon-image" in (item.get("layout") or {})
        )
        self.assertEqual(symbol["layout"]["icon-image"][0], "match")
        self.assertEqual(symbol["layout"]["icon-image"][1], ["to-string", ["get", "station_type"]])
        self.assertEqual(symbol["paint"]["icon-color"][0], "match")
        self.assertEqual(symbol["layout"]["icon-size"][0], "interpolate")
        self.assertTrue(symbol["layout"]["icon-allow-overlap"])
        self.assertTrue(symbol["layout"]["icon-ignore-placement"])
        self.assertFalse(needs_glyphs)  # icons alone do not need glyphs
        self.assertIn("gl-underground", icons)
        self.assertIn("gl-station", icons)

    def test_point_circles_and_lines_scale_with_zoom(self):
        from apps.layers.share_style import build_layer_paint_layers

        owner = get_user_model().objects.create_user("zoom", "zoom@example.com", "pw-12345!")
        points = LayerInfo.objects.create(
            owner=owner,
            name="Stops",
            schema_name="layers_data",
            table_name="layer_" + "f" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            style={"color": "#0F2D53", "opacity": 0.8},
        )
        lines = LayerInfo.objects.create(
            owner=owner,
            name="Corridors",
            schema_name="layers_data",
            table_name="layer_" + "a" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            style={"color": "#2563EB", "strokeWidth": 4, "opacity": 1},
            label_config={"field": "name", "size": 12, "color": "#0F2D53"},
        )
        circle = build_layer_paint_layers(layer=points, source_id="s")[0][0]
        self.assertEqual(circle["paint"]["circle-radius"][0], "interpolate")
        line_layers, needs_glyphs, _icons = build_layer_paint_layers(layer=lines, source_id="s")
        line = next(item for item in line_layers if item["type"] == "line")
        label = next(item for item in line_layers if item["id"].endswith("-label"))
        self.assertEqual(line["paint"]["line-width"][0], "interpolate")
        self.assertTrue(needs_glyphs)
        self.assertEqual(label["minzoom"], 9)  # sparse default feature_count
        self.assertFalse(label["layout"]["text-allow-overlap"])
        self.assertEqual(label["layout"]["symbol-placement"], "line")
        self.assertEqual(label["layout"]["text-size"][0], "interpolate")

    def test_density_scales_point_icons_and_line_width(self):
        from apps.layers.share_style import build_layer_paint_layers, _density_profile

        owner = get_user_model().objects.create_user("dens", "dens@example.com", "pw-12345!")
        sparse = LayerInfo.objects.create(
            owner=owner,
            name="Sparse POIs",
            schema_name="layers_data",
            table_name="layer_" + "b" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            feature_count=80,
            style={"color": "#0F2D53", "marker": {"type": "icon", "icon": "gl-station"}},
        )
        dense = LayerInfo.objects.create(
            owner=owner,
            name="Dense POIs",
            schema_name="layers_data",
            table_name="layer_" + "1" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            feature_count=3010,
            style={"color": "#0F2D53", "marker": {"type": "icon", "icon": "gl-bus"}},
        )
        sparse_line = LayerInfo.objects.create(
            owner=owner,
            name="Sparse lines",
            schema_name="layers_data",
            table_name="layer_" + "2" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            feature_count=6,
            style={"color": "#00ADE5", "strokeWidth": 3, "opacity": 1},
        )
        medium_line = LayerInfo.objects.create(
            owner=owner,
            name="Medium lines",
            schema_name="layers_data",
            table_name="layer_" + "3" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            feature_count=117,
            style={"color": "#2563EB", "strokeWidth": 3, "opacity": 1},
        )
        self.assertEqual(_density_profile(80)["tier"], "sparse")
        self.assertEqual(_density_profile(3010)["tier"], "very_dense")
        sparse_layers = build_layer_paint_layers(layer=sparse, source_id="s")[0]
        dense_layers = build_layer_paint_layers(layer=dense, source_id="s")[0]
        sparse_icon = next(item for item in sparse_layers if item["id"].endswith("-symbol"))
        dense_icon = next(item for item in dense_layers if item["id"].endswith("-symbol"))
        # Always visible (no minzoom hide); dense smaller/softer at overview, grows on zoom.
        self.assertNotIn("minzoom", sparse_icon)
        self.assertNotIn("minzoom", dense_icon)
        self.assertFalse(any(item["id"].endswith("-overview") for item in dense_layers))
        self.assertGreater(
            sparse_icon["layout"]["icon-size"][4],
            dense_icon["layout"]["icon-size"][4],
        )
        self.assertGreaterEqual(dense_icon["layout"]["icon-size"][4], 0.2)
        self.assertEqual(dense_icon["paint"]["icon-opacity"][0], "interpolate")
        sparse_w = build_layer_paint_layers(layer=sparse_line, source_id="s")[0][0]["paint"]["line-width"]
        medium_w = build_layer_paint_layers(layer=medium_line, source_id="s")[0][0]["paint"]["line-width"]
        self.assertGreater(sparse_w[4], medium_w[4])

    def test_marker_size_scales_icons_and_circles(self):
        from apps.layers.share_style import build_layer_paint_layers

        owner = get_user_model().objects.create_user("msize", "msize@example.com", "pw-12345!")
        base = {
            "owner": owner,
            "schema_name": "layers_data",
            "geometry_type": LayerInfo.GeometryType.POINT,
            "feature_count": 80,
        }
        icon_default = LayerInfo.objects.create(
            **base,
            name="Icon default",
            table_name="layer_" + "c" * 32,
            style={"color": "#0F2D53", "marker": {"type": "icon", "icon": "gl-metro"}},
        )
        icon_large = LayerInfo.objects.create(
            **base,
            name="Icon large",
            table_name="layer_" + "d" * 32,
            style={
                "color": "#0F2D53",
                "marker": {"type": "icon", "icon": "gl-metro", "size": 2},
            },
        )
        circle_default = LayerInfo.objects.create(
            **base,
            name="Circle default",
            table_name="layer_" + "0" * 32,
            style={"color": "#0F2D53", "marker": {"type": "circle", "size": 1}},
        )
        circle_large = LayerInfo.objects.create(
            **base,
            name="Circle large",
            table_name="layer_" + "e" * 32,
            style={"color": "#0F2D53", "marker": {"type": "circle", "size": 1.5}},
        )
        default_size = build_layer_paint_layers(layer=icon_default, source_id="s")[0][0][
            "layout"
        ]["icon-size"]
        large_size = build_layer_paint_layers(layer=icon_large, source_id="s")[0][0]["layout"][
            "icon-size"
        ]
        circle_base = build_layer_paint_layers(layer=circle_default, source_id="s")[0][0][
            "paint"
        ]["circle-radius"]
        circle_radius = build_layer_paint_layers(layer=circle_large, source_id="s")[0][0][
            "paint"
        ]["circle-radius"]
        self.assertEqual(default_size[0], "interpolate")
        self.assertEqual(large_size[0], "interpolate")
        self.assertEqual(circle_radius[0], "interpolate")
        # Stop values are scaled in place (zoom must stay top-level for Mapbox).
        self.assertAlmostEqual(large_size[4], default_size[4] * 2, places=4)
        self.assertAlmostEqual(circle_radius[4], circle_base[4] * 1.5, places=4)

    def test_icon_by_category_sizes_use_match_inside_zoom_stops(self):
        from apps.layers.share_style import build_layer_paint_layers

        owner = get_user_model().objects.create_user("isz", "isz@example.com", "pw-12345!")
        layer = LayerInfo.objects.create(
            owner=owner,
            name="Sized icons",
            schema_name="layers_data",
            table_name="layer_" + "9" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            feature_count=80,
            style={
                "color": "#0F2D53",
                "marker": {
                    "type": "icon",
                    "icon": "gl-poi",
                    "size": 1,
                    "iconBy": {
                        "field": "station_type",
                        "default": "gl-poi",
                        "categories": {
                            "metro": {"icon": "gl-metro", "size": 2},
                            "bus": {"icon": "gl-bus", "size": 0.5},
                        },
                    },
                },
            },
            attribute_schema=[{"name": "station_type", "type": "text"}],
        )
        symbol = build_layer_paint_layers(layer=layer, source_id="s")[0][0]
        icon_size = symbol["layout"]["icon-size"]
        self.assertEqual(icon_size[0], "interpolate")
        self.assertEqual(icon_size[2], ["zoom"])
        first_stop = icon_size[4]
        self.assertEqual(first_stop[0], "match")
        self.assertEqual(first_stop[1], ["to-string", ["get", "station_type"]])
        # metro=2x, bus=0.5x relative to the density stop baseline.
        metro_idx = first_stop.index("metro")
        bus_idx = first_stop.index("bus")
        self.assertAlmostEqual(first_stop[metro_idx + 1] / first_stop[bus_idx + 1], 4.0, places=4)
        self.assertEqual(symbol["layout"]["icon-image"][0], "match")

    def test_share_style_exposes_required_icons(self):
        from apps.layers.share_style import build_share_style

        owner = get_user_model().objects.create_user("shr", "shr@example.com", "pw-12345!")
        layer = LayerInfo.objects.create(
            owner=owner,
            name="POIs",
            schema_name="layers_data",
            table_name="layer_" + "e" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            style={
                "color": "#0F2D53",
                "marker": {"type": "icon", "icon": "gl-bus"},
            },
        )
        doc = build_share_style(layer=layer, tiles_url="http://example/x/tok/{z}/{x}/{y}.pbf")
        self.assertEqual(doc["metadata"]["geolayers:required_icons"], ["gl-bus"])
        self.assertEqual(doc["metadata"]["geolayers:legend"], [])
        self.assertEqual(doc["metadata"]["geolayers:kind"], "layer")
        symbol = next(item for item in doc["layers"] if item["type"] == "symbol")
        self.assertEqual(symbol["layout"]["icon-image"], "gl-bus")

    def test_share_style_includes_viewport_from_bounds(self):
        from apps.layers.share_style import build_share_style

        owner = get_user_model().objects.create_user("vp", "vp@example.com", "pw-12345!")
        layer = LayerInfo.objects.create(
            owner=owner,
            name="Bounded",
            schema_name="layers_data",
            table_name="layer_" + "f" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
            bounds=[46.5, 24.5, 47.0, 25.0],
            style={"color": "#0F2D53"},
        )
        doc = build_share_style(layer=layer, tiles_url="http://example/x/tok/{z}/{x}/{y}.pbf")
        self.assertEqual(doc["center"], [46.75, 24.75])
        self.assertIn("zoom", doc)
        self.assertEqual(doc["metadata"]["geolayers:bounds"], [46.5, 24.5, 47.0, 25.0])

    def test_style_legend_from_color_and_icon_by(self):
        from apps.layers.share_style import build_style_legend

        legend = build_style_legend(
            {
                "color": "#888888",
                "colorBy": {
                    "field": "station_type",
                    "default": "#888888",
                    "categories": {"underground": "#2563eb", "surface": "#16a34a"},
                },
                "marker": {
                    "type": "icon",
                    "icon": "gl-station",
                    "iconBy": {
                        "field": "station_type",
                        "default": "gl-station",
                        "categories": {
                            "underground": "gl-underground",
                            "surface": "gl-station",
                        },
                    },
                },
            },
            title="Stations",
        )
        self.assertEqual(legend["title"], "Stations")
        self.assertEqual(legend["field"], "station_type")
        self.assertEqual(len(legend["items"]), 2)
        by_label = {item["label"]: item for item in legend["items"]}
        self.assertEqual(by_label["underground"]["color"], "#2563eb")
        self.assertEqual(by_label["underground"]["icon"], "gl-underground")
        self.assertEqual(by_label["underground"]["swatch"], "icon")
        self.assertEqual(
            set(by_label["underground"].keys()),
            {"label", "color", "swatch", "icon"},
        )
        self.assertIsNone(
            build_style_legend({"color": "#0F2D53", "marker": {"type": "circle"}})
        )
        line_legend = build_style_legend(
            {
                "colorBy": {
                    "field": "metro_line",
                    "categories": {"Blue": "#2563eb", "Green": "#16a34a"},
                }
            },
            title="Metro Lines",
            geometry_type="LineString",
        )
        self.assertEqual(line_legend["items"][0]["swatch"], "line")

        # Split fields: icon-shape rows only (colors live on the line layer).
        split = build_style_legend(
            {
                "color": "#0F2D53",
                "colorBy": {
                    "field": "metro_line",
                    "categories": {"Red line": "#dc2626", "Blue line": "#2563eb"},
                },
                "marker": {
                    "type": "icon",
                    "icon": "gl-metro",
                    "iconBy": {
                        "field": "station_type",
                        "categories": {
                            "At Grade": "gl-station",
                            "Deep Underground": "gl-triangle",
                        },
                    },
                },
            },
            title="Metro Stations",
            geometry_type="Point",
        )
        self.assertEqual(split["field"], "station_type")
        self.assertEqual(len(split["items"]), 2)
        self.assertEqual(split["items"][0]["swatch"], "icon")
        self.assertEqual(split["items"][0]["icon"], "gl-station")
        self.assertEqual(split["items"][0]["color"], "#0F2D53")
        self.assertEqual(
            set(split["items"][0].keys()),
            {"label", "color", "swatch", "icon"},
        )



# ---------------------------------------------------------------------------------------------
# PostGIS-only: the real SQL tile function (migration 0003) and the load-test fixture
# ---------------------------------------------------------------------------------------------
@skipUnless(connection.vendor == "postgresql", "needs PostGIS (layers_data.geolayers_tile)")
class GeolayersTileFunctionTests(TestCase):
    table = "layer_" + "c" * 32

    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS layers_data")
            cursor.execute(
                f'CREATE TABLE layers_data."{self.table}" (id serial PRIMARY KEY, name text, '
                "geom geometry(MultiPoint, 4326))"
            )
            cursor.execute(
                f'INSERT INTO layers_data."{self.table}" (name, geom) VALUES '
                "('a', ST_Multi(ST_SetSRID(ST_MakePoint(46.7, 24.7), 4326)))"
            )

    def _tile(self, z, x, y, params):
        with connection.cursor() as cursor:
            cursor.execute("SELECT layers_data.geolayers_tile(%s, %s, %s, %s::json)", [z, x, y, json.dumps(params)])
            value = cursor.fetchone()[0]
        return bytes(value) if value is not None else None

    def test_returns_mvt_named_after_table_with_properties(self):
        tile = self._tile(0, 0, 0, {"layer": self.table})
        self.assertTrue(tile)
        self.assertIn(self.table.encode(), tile)  # MVT layer name = table name (= source-layer)
        self.assertIn(b"name", tile)  # attribute columns become properties

    def test_tile_without_data_is_empty(self):
        self.assertFalse(self._tile(10, 300, 400, {"layer": self.table}))  # over the Atlantic

    def test_rejects_non_layer_tables_and_injection(self):
        for params in (
            {},
            {"layer": "spatial_ref_sys"},
            {"layer": "layer_" + "d" * 32},  # well-formed but missing
            {"layer": f'{self.table}"; DROP TABLE layers_data."{self.table}'},
        ):
            self.assertIsNone(self._tile(0, 0, 0, params), params)
        self.assertTrue(self._tile(0, 0, 0, {"layer": self.table}))  # table survived


@skipUnless(connection.vendor == "postgresql", "fixture creates a PostGIS table")
class LoadtestFixtureCommandTests(TestCase):
    def test_creates_real_layer_and_share_link_then_cleans_up(self):
        out = StringIO()
        call_command("tile_loadtest_fixture", "--points", "50", stdout=out)
        data = json.loads(out.getvalue())
        layer = LayerInfo.objects.get(table_name=data["layer_table"])
        self.assertEqual(layer.feature_count, 50)
        self.assertEqual(check_share_link(data["share_token"])[1], "")

        call_command("tile_loadtest_fixture", "--cleanup", stdout=StringIO())
        self.assertFalse(LayerInfo.objects.filter(pk=layer.pk).exists())
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", [f"layers_data.{data['layer_table']}"])
            self.assertIsNone(cursor.fetchone()[0])
