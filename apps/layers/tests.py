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
        self.assertEqual(body["xyz_url"], f"http://testserver/x/{body['token']}/{{z}}/{{x}}/{{y}}.pbf")
        self.assertEqual(body["total_requests"], 0)
        self.assertIsNone(body["last_used_at"])
        self.assertFalse(body["never_expires"])
        self.assertEqual(body["source_layer"], TABLE)
        self.assertIn("geometry_type", body)

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
        self.assertEqual((listed[0]["total_requests"], listed[0]["requests_last_30_days"]), (12, 7))

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
