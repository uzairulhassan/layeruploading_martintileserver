from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.layers.models import LayerInfo
from apps.layers.tile_auth import authorize_tile_request

from .models import MapLayer, MapProject, MapShare, MapShareLink
from .share_style import build_map_share_style
from .stack_order import apply_recommended_stack_order, geometry_stack_rank

SECRET = "test-geolayers-secret"
TABLE_A = "layer_" + "a" * 32
TABLE_B = "layer_" + "b" * 32


@override_settings(TILE_AUTH_SHARED_SECRET=SECRET, MARTIN_LAYER_FUNCTION="geolayers_tile")
class MapShareAuthTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.owner = users.create_user("mapowner", "mapowner@example.com", "pw-12345!")
        self.stranger = users.create_user("stranger2", "stranger2@example.com", "pw-12345!")
        self.layer_a = LayerInfo.objects.create(
            owner=self.owner,
            name="A",
            schema_name="layers_data",
            table_name=TABLE_A,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            attribute_schema=[{"name": "name", "type": "text"}],
            label_config={"field": "name"},
        )
        self.layer_b = LayerInfo.objects.create(
            owner=self.owner, name="B", schema_name="layers_data", table_name=TABLE_B
        )
        self.map = MapProject.objects.create(owner=self.owner, name="Ops map", center_lng=46.7, center_lat=24.7, zoom=10)
        MapLayer.objects.create(map=self.map, layer=self.layer_a, order=0, visible=True, opacity=1.0)
        MapLayer.objects.create(map=self.map, layer=self.layer_b, order=1, visible=False, opacity=0.5)
        self.factory = RequestFactory()

    def _link(self, **kwargs):
        kwargs.setdefault("expires_at", timezone.now() + timedelta(days=1))
        return MapShareLink.objects.create(map=self.map, created_by=self.owner, **kwargs)

    def _decide(self, uri):
        request = self.factory.get("/tiles-auth/validate/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        return authorize_tile_request(request, uri)

    def test_map_share_allows_visible_tables_on_the_map(self):
        link = self._link()
        decision = self._decide(f"/m/{link.token}/{TABLE_A}/3/4/5.pbf")
        self.assertEqual(decision.status, 204)
        self.assertEqual(decision.layer_table, TABLE_A)
        self.assertNotIn(link.token, decision.token_label)

    def test_map_share_refuses_hidden_tables(self):
        link = self._link()
        decision = self._decide(f"/m/{link.token}/{TABLE_B}/3/4/5.pbf")
        self.assertEqual((decision.status, decision.reason), (403, "forbidden"))

    def test_map_share_refuses_table_not_on_map(self):
        link = self._link()
        other = "layer_" + "c" * 32
        decision = self._decide(f"/m/{link.token}/{other}/3/4/5.pbf")
        self.assertEqual((decision.status, decision.reason), (403, "forbidden"))

    def test_map_share_refusals(self):
        expired = self._link(expires_at=timezone.now() - timedelta(minutes=1))
        blocked = self._link(is_blocked=True)
        cases = {
            "/m/does-not-exist/" + TABLE_A + "/3/4/5.pbf": "not_found",
            f"/m/{expired.token}/{TABLE_A}/3/4/5.pbf": "expired",
            f"/m/{blocked.token}/{TABLE_A}/3/4/5.pbf": "blocked",
        }
        for uri, reason in cases.items():
            decision = self._decide(uri)
            self.assertEqual((decision.status, decision.reason), (403, reason), uri)

    def test_removing_layer_from_map_stops_tiles(self):
        link = self._link()
        uri = f"/m/{link.token}/{TABLE_A}/3/4/5.pbf"
        self.assertEqual(self._decide(uri).status, 204)
        MapLayer.objects.filter(map=self.map, layer=self.layer_a).delete()
        decision = self._decide(uri)
        self.assertEqual((decision.status, decision.reason), (403, "forbidden"))

    def test_style_document_includes_visible_layers_and_viewport(self):
        link = self._link()
        self.layer_a.bounds = [46.5, 24.5, 47.0, 25.0]
        self.layer_a.save(update_fields=["bounds"])

        def tiles_url(table):
            return f"https://example.test/m/{link.token}/{table}/{{z}}/{{x}}/{{y}}.pbf"

        doc = build_map_share_style(map_project=self.map, tiles_url_for_table=tiles_url)
        self.assertEqual(doc["version"], 8)
        self.assertEqual(doc["name"], "Ops map")
        # Custom saved viewport is preserved; bounds still published for fit tools.
        self.assertEqual(doc["center"], [46.7, 24.7])
        self.assertEqual(doc["zoom"], 10)
        self.assertEqual(doc["metadata"]["geolayers:bounds"], [46.5, 24.5, 47.0, 25.0])
        self.assertIn("basemap-osm", doc["sources"])
        self.assertIn(f"src-{TABLE_A}", doc["sources"])
        self.assertNotIn(f"src-{TABLE_B}", doc["sources"])
        self.assertEqual(doc["metadata"]["geolayers:kind"], "map")
        meta_a = next(item for item in doc["metadata"]["geolayers:layers"] if item["table"] == TABLE_A)
        self.assertEqual(meta_a["name"], "A")
        self.assertEqual(meta_a["geometry_type"], "LineString")
        self.assertEqual(meta_a["attribute_schema"], [{"name": "name", "type": "text"}])
        self.assertEqual(meta_a["label_field"], "name")
        self.assertFalse(any(item["table"] == TABLE_B for item in doc["metadata"]["geolayers:layers"]))
        self.assertFalse(any(layer["id"].startswith(TABLE_B) for layer in doc["layers"] if layer.get("id")))

    def test_default_viewport_uses_union_bounds(self):
        self.map.center_lng = 0
        self.map.center_lat = 0
        self.map.zoom = 2
        self.map.save(update_fields=["center_lng", "center_lat", "zoom"])
        self.layer_a.bounds = [46.0, 24.0, 48.0, 26.0]
        self.layer_a.save(update_fields=["bounds"])

        doc = build_map_share_style(
            map_project=self.map,
            tiles_url_for_table=lambda table: f"https://example.test/m/tok/{table}/{{z}}/{{x}}/{{y}}.pbf",
        )
        self.assertEqual(doc["metadata"]["geolayers:bounds"], [46.0, 24.0, 48.0, 26.0])
        self.assertEqual(doc["center"], [47.0, 25.0])
        self.assertGreater(doc["zoom"], 2)

    def test_map_share_grants_app_tiles_without_layer_share(self):
        """In-app MapShare alone is enough to load composition tiles."""
        MapShare.objects.create(
            map=self.map,
            shared_with=self.stranger,
            shared_by=self.owner,
            permission=MapShare.Permission.VIEW,
        )
        request = self.factory.get("/tiles-auth/validate/")
        request.user = self.stranger
        decision = authorize_tile_request(
            request, f"/tiles/geolayers_tile/3/4/5?layer={TABLE_A}"
        )
        self.assertEqual(decision.status, 204)
        self.assertEqual(decision.layer_table, TABLE_A)


@override_settings(TILE_AUTH_SHARED_SECRET=SECRET)
class MapShareLinkApiTests(TestCase):
    def setUp(self):
        from apps.accounts.roles import ensure_user_role

        users = get_user_model().objects
        self.owner = users.create_user("apiowner", "apiowner@example.com", "pw-12345!")
        self.other = users.create_user("apiother", "apiother@example.com", "pw-12345!")
        self.owner.roles.add(ensure_user_role())
        self.map = MapProject.objects.create(owner=self.owner, name="API map")
        self.client = APIClient()

    def test_owner_can_create_list_and_revoke_share_links(self):
        visible = LayerInfo.objects.create(
            owner=self.owner, name="Vis", schema_name="layers_data", table_name="layer_" + "d" * 32
        )
        hidden = LayerInfo.objects.create(
            owner=self.owner, name="Hid", schema_name="layers_data", table_name="layer_" + "e" * 32
        )
        MapLayer.objects.create(map=self.map, layer=visible, order=0, visible=True)
        MapLayer.objects.create(map=self.map, layer=hidden, order=1, visible=False)

        self.client.force_authenticate(self.owner)
        create = self.client.post(
            f"/api/maps/{self.map.id}/share-links/",
            {"expires_at": None},
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        self.assertIn("/m/", create.data["style_url"])
        self.assertTrue(create.data["style_url"].endswith("/style.json"))
        self.assertTrue(create.data["never_expires"])
        self.assertEqual(create.data["layer_count"], 1)

        listed = self.client.get(f"/api/maps/{self.map.id}/share-links/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["layer_count"], 1)

        link_id = create.data["id"]
        revoke = self.client.delete(f"/api/maps/{self.map.id}/share-links/{link_id}/")
        self.assertEqual(revoke.status_code, 204)
        self.assertFalse(MapShareLink.objects.filter(id=link_id).exists())

    def test_non_owner_cannot_manage_share_links(self):
        self.client.force_authenticate(self.other)
        res = self.client.post(f"/api/maps/{self.map.id}/share-links/", {}, format="json")
        self.assertIn(res.status_code, (403, 404))


class MapLayerStyleLayersApiTests(TestCase):
    """In-app map builder consumes ``style_layers`` from the same paint builder as shares."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user("styleowner", "styleowner@example.com", "pw-12345!")
        self.layer = LayerInfo.objects.create(
            owner=self.owner,
            name="Styled",
            schema_name="layers_data",
            table_name="layer_" + "f" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
            style={"color": "#112233", "opacity": 0.7, "strokeWidth": 4},
        )
        self.map = MapProject.objects.create(owner=self.owner, name="Style map")
        self.map_layer = MapLayer.objects.create(
            map=self.map, layer=self.layer, order=0, visible=True, opacity=0.5
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_map_payload_includes_server_built_style_layers(self):
        body = self.client.get(f"/api/maps/{self.map.id}/").json()
        map_layer = body["map_layers"][0]
        self.assertTrue(map_layer["style_layers"])
        line = map_layer["style_layers"][0]
        self.assertEqual(line["id"], f"layer-{self.map_layer.id}-line")
        self.assertEqual(line["source"], f"src-{self.layer.id}")
        self.assertEqual(line["source-layer"], self.layer.table_name)
        self.assertEqual(line["paint"]["line-color"], "#112233")
        self.assertEqual(line["paint"]["line-opacity"], 0.5)
        self.assertEqual(line["paint"]["line-width"][0], "interpolate")
        self.assertEqual(map_layer["required_icons"], [])
        # No categorical style → no legend block.
        self.assertIsNone(map_layer["legend"])

    def test_map_payload_includes_server_built_legend(self):
        self.layer.style = {
            "colorBy": {
                "field": "metro_line",
                "categories": {"Blue": "#2563eb", "Green": "#16a34a"},
            }
        }
        self.layer.save(update_fields=["style"])
        body = self.client.get(f"/api/maps/{self.map.id}/").json()
        legend = body["map_layers"][0]["legend"]
        self.assertEqual(legend["title"], "Styled")
        self.assertEqual(legend["items"][0]["swatch"], "line")
        self.assertEqual(legend["items"][0]["color"], "#2563eb")


class MapStackOrderTests(TestCase):
    """Zones under routes under POIs — recommended stack for clickability."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user("stack", "stack@example.com", "pw-12345!")
        self.zone = LayerInfo.objects.create(
            owner=self.owner,
            name="Zone",
            schema_name="layers_data",
            table_name="layer_" + "1" * 32,
            geometry_type=LayerInfo.GeometryType.POLYGON,
        )
        self.route = LayerInfo.objects.create(
            owner=self.owner,
            name="Route",
            schema_name="layers_data",
            table_name="layer_" + "2" * 32,
            geometry_type=LayerInfo.GeometryType.LINESTRING,
        )
        self.poi = LayerInfo.objects.create(
            owner=self.owner,
            name="POI",
            schema_name="layers_data",
            table_name="layer_" + "3" * 32,
            geometry_type=LayerInfo.GeometryType.POINT,
        )
        self.map = MapProject.objects.create(owner=self.owner, name="Stack map")
        # Intentionally wrong order: POI at bottom, zone on top.
        MapLayer.objects.create(map=self.map, layer=self.poi, order=0)
        MapLayer.objects.create(map=self.map, layer=self.route, order=1)
        MapLayer.objects.create(map=self.map, layer=self.zone, order=2)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_geometry_stack_rank(self):
        self.assertEqual(geometry_stack_rank("Polygon"), 0)
        self.assertEqual(geometry_stack_rank("LineString"), 1)
        self.assertEqual(geometry_stack_rank("Point"), 2)

    def test_apply_recommended_stack_order_api(self):
        res = self.client.post(f"/api/maps/{self.map.id}/apply-recommended-order/", {}, format="json")
        self.assertEqual(res.status_code, 200)
        by_name = {row["layer_detail"]["name"]: row["order"] for row in res.json()}
        self.assertLess(by_name["Zone"], by_name["Route"])
        self.assertLess(by_name["Route"], by_name["POI"])

    def test_apply_recommended_stack_order_helper(self):
        ordered = apply_recommended_stack_order(self.map)
        names = [ml.layer.name for ml in ordered]
        self.assertEqual(names, ["Zone", "Route", "POI"])
