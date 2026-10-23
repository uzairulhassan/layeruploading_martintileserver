from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.layers.models import LayerInfo
from apps.layers.tile_auth import authorize_tile_request

from .models import MapLayer, MapProject, MapShareLink
from .share_style import build_map_share_style

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
            owner=self.owner, name="A", schema_name="layers_data", table_name=TABLE_A
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

    def test_map_share_allows_tables_on_the_map(self):
        link = self._link()
        for table in (TABLE_A, TABLE_B):
            decision = self._decide(f"/m/{link.token}/{table}/3/4/5.pbf")
            self.assertEqual(decision.status, 204, table)
            self.assertEqual(decision.layer_table, table)
            self.assertNotIn(link.token, decision.token_label)

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
        uri = f"/m/{link.token}/{TABLE_B}/3/4/5.pbf"
        self.assertEqual(self._decide(uri).status, 204)
        MapLayer.objects.filter(map=self.map, layer=self.layer_b).delete()
        decision = self._decide(uri)
        self.assertEqual((decision.status, decision.reason), (403, "forbidden"))

    def test_style_document_includes_layers_and_viewport(self):
        link = self._link()

        def tiles_url(table):
            return f"https://example.test/m/{link.token}/{table}/{{z}}/{{x}}/{{y}}.pbf"

        doc = build_map_share_style(map_project=self.map, tiles_url_for_table=tiles_url)
        self.assertEqual(doc["version"], 8)
        self.assertEqual(doc["name"], "Ops map")
        self.assertEqual(doc["center"], [46.7, 24.7])
        self.assertEqual(doc["zoom"], 10)
        self.assertIn("basemap-osm", doc["sources"])
        self.assertIn(f"src-{TABLE_A}", doc["sources"])
        self.assertIn(f"src-{TABLE_B}", doc["sources"])
        self.assertEqual(doc["metadata"]["geolayers:kind"], "map")
        # Hidden layer still present with visibility none (stays synced when toggled).
        hidden = next(layer for layer in doc["layers"] if layer["id"].startswith(TABLE_B))
        self.assertEqual(hidden["layout"]["visibility"], "none")


@override_settings(TILE_AUTH_SHARED_SECRET=SECRET)
class MapShareLinkApiTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.owner = users.create_user("apiowner", "apiowner@example.com", "pw-12345!")
        self.other = users.create_user("apiother", "apiother@example.com", "pw-12345!")
        self.map = MapProject.objects.create(owner=self.owner, name="API map")
        self.client = APIClient()

    def test_owner_can_create_list_and_revoke_share_links(self):
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

        listed = self.client.get(f"/api/maps/{self.map.id}/share-links/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        link_id = create.data["id"]
        revoke = self.client.delete(f"/api/maps/{self.map.id}/share-links/{link_id}/")
        self.assertEqual(revoke.status_code, 204)
        self.assertFalse(MapShareLink.objects.filter(id=link_id).exists())

    def test_non_owner_cannot_manage_share_links(self):
        self.client.force_authenticate(self.other)
        res = self.client.post(f"/api/maps/{self.map.id}/share-links/", {}, format="json")
        self.assertIn(res.status_code, (403, 404))
