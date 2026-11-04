"""KML/KMZ uploads: style parsing, the split-by-geometry import, groups, and map/style integration."""
import io
import shutil
import uuid
import zipfile
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.maps.models import MapProject

from . import kml_style
from .kml_import import import_kml
from .models import LayerGroup, LayerInfo, LayerShare
from .services import LayerImportError, delete_layer
from .share_style import build_layer_paint_layers
from .tile_auth import user_can_view_layer

HAS_OGR2OGR = shutil.which(settings.OGR2OGR_PATH) is not None

# Two folders, shared + inline styles, a StyleMap, ExtendedData, 3D coordinates and
# a mixed MultiGeometry. Expected split: 2 points, 3 lines, 3 polygons.
SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Sample</name>
  <Style id="redLine"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>
  <Style id="bluePoly"><LineStyle><color>ffff0000</color><width>1</width></LineStyle><PolyStyle><color>7fff0000</color></PolyStyle></Style>
  <Style id="pinN"><IconStyle><color>ff00ff00</color></IconStyle></Style>
  <Style id="pinH"><IconStyle><color>ff00ffff</color></IconStyle></Style>
  <StyleMap id="pin"><Pair><key>normal</key><styleUrl>#pinN</styleUrl></Pair><Pair><key>highlight</key><styleUrl>#pinH</styleUrl></Pair></StyleMap>
  <Folder><name>Sites "A"</name>
    <Placemark><name>P1</name><description><![CDATA[<b>hi</b>]]></description><styleUrl>#pin</styleUrl>
      <ExtendedData><Data name="kind"><value>shop</value></Data></ExtendedData>
      <Point><coordinates>46.7,24.7,10</coordinates></Point></Placemark>
    <Placemark><name>L1</name><styleUrl>#redLine</styleUrl><LineString><coordinates>46.7,24.7,0 46.8,24.8,0</coordinates></LineString></Placemark>
    <Placemark><name>L2</name><styleUrl>#redLine</styleUrl><LineString><coordinates>46.71,24.7 46.81,24.8</coordinates></LineString></Placemark>
  </Folder>
  <Folder><name>Areas</name>
    <Placemark><name>Poly1</name><styleUrl>#bluePoly</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>46.6,24.6 46.7,24.6 46.7,24.7 46.6,24.6</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
    <Placemark><name>Poly2</name><styleUrl>#bluePoly</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>46.8,24.6 46.9,24.6 46.9,24.7 46.8,24.6</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
    <Placemark><name>Mixed</name><Style><LineStyle><color>ff00a5ff</color></LineStyle><PolyStyle><color>8000a5ff</color></PolyStyle></Style>
      <MultiGeometry><Point><coordinates>46.65,24.65</coordinates></Point><LineString><coordinates>46.6,24.6 46.61,24.61</coordinates></LineString>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>46.5,24.5 46.55,24.5 46.55,24.55 46.5,24.5</coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry></Placemark>
  </Folder>
</Document>
</kml>
"""

LINES_ONLY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark><name>Only</name><LineString><coordinates>46.7,24.7 46.8,24.8</coordinates></LineString></Placemark>
</Document></kml>
"""

EMPTY_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Nothing here</name>
  <Folder><name>Empty</name></Folder>
</Document></kml>
"""


def _kml_upload(content=SAMPLE_KML, name="sample.kml"):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="application/vnd.google-earth.kml+xml")


def _kmz_upload(content=SAMPLE_KML, name="sample.kmz"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("doc.kml", content)
        zf.writestr("files/icon.png", b"not really a png")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/vnd.google-earth.kmz")


def _layers_data_tables():
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'layers_data'")
        return {row[0] for row in cursor.fetchall()}


def _columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'layers_data' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


# --------------------------------------------------------------------------- style parsing
class KmlStyleParsingTests(SimpleTestCase):
    def test_pen_brush_and_symbol_are_parsed_with_alpha(self):
        parsed = kml_style.parse_ogr_style("PEN(c:#FF0000FF,w:3.000000px);BRUSH(fc:#0000FF7F)")
        self.assertEqual(parsed["pen_color"].hex, "#ff0000")
        self.assertEqual(parsed["pen_width"], 3.0)
        self.assertEqual(parsed["brush_color"].hex, "#0000ff")
        self.assertAlmostEqual(parsed["brush_color"].alpha, 127 / 255)
        self.assertEqual(kml_style.parse_ogr_style("SYMBOL(c:#00FF00FF,s:1.1)")["symbol_color"].hex, "#00ff00")

    def test_six_digit_colour_is_opaque_and_unresolved_reference_is_ignored(self):
        self.assertEqual(kml_style.parse_ogr_style("PEN(c:#123456)")["pen_color"].alpha, 1.0)
        self.assertEqual(kml_style.parse_ogr_style("@redLine"), {})
        self.assertEqual(kml_style.parse_ogr_style(None), {})
        self.assertEqual(kml_style.parse_ogr_style("LABEL(t:\"PEN(c:#FF0000)\")"), {})

    def test_width_is_clamped(self):
        self.assertEqual(kml_style.parse_ogr_style("PEN(c:#FF0000,w:0px)")["pen_width"], kml_style.MIN_WIDTH)
        self.assertEqual(kml_style.parse_ogr_style("PEN(c:#FF0000,w:99pt)")["pen_width"], kml_style.MAX_WIDTH)

    def test_feature_columns_read_the_tools_each_family_draws(self):
        style = "PEN(c:#FF0000FF,w:2px);BRUSH(fc:#0000FF80);SYMBOL(c:#00FF00FF)"
        self.assertEqual(
            kml_style.feature_columns(style, kml_style.POINT),
            {"kml_color": "rgba(0,255,0,1.0)", "kml_stroke": None, "kml_width": None},
        )
        self.assertEqual(
            kml_style.feature_columns(style, kml_style.LINE),
            {"kml_color": "rgba(255,0,0,1.0)", "kml_stroke": None, "kml_width": 2.0},
        )
        self.assertEqual(
            kml_style.feature_columns(style, kml_style.POLYGON),
            {"kml_color": "rgba(0,0,255,0.502)", "kml_stroke": "rgba(255,0,0,1.0)", "kml_width": 2.0},
        )

    def test_layer_style_uses_existing_style_keys(self):
        style = kml_style.layer_style(
            "PEN(c:#0000FFFF,w:1px);BRUSH(fc:#0000FF7F)", kml_style.POLYGON, use_source_colors=True
        )
        self.assertEqual(
            style,
            {"color": "#0000ff", "opacity": 0.5, "strokeColor": "#0000ff", "strokeWidth": 1.0, "useSourceColors": True},
        )
        self.assertEqual(kml_style.layer_style(None, kml_style.LINE, use_source_colors=False), {})


# --------------------------------------------------------------------------- import (real ogr2ogr + PostGIS)
@skipUnless(HAS_OGR2OGR, "ogr2ogr (GDAL) is required for KML import tests")
class KmlImportTests(TransactionTestCase):
    """TransactionTestCase: ogr2ogr writes the staging table over its own connection."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user("kmlowner", "kmlowner@example.com", "pw-12345!")
        self.tables_before = _layers_data_tables()

    def tearDown(self):
        with connection.cursor() as cursor:
            for table in _layers_data_tables() - self.tables_before:
                cursor.execute(f'DROP TABLE IF EXISTS layers_data."{table}" CASCADE')

    def _import(self, upload):
        return import_kml(owner=self.owner, name="Survey", description="field data", uploaded_file=upload)

    def _layers_by_type(self, group):
        return {layer.geometry_type: layer for layer in group.layers.all()}

    def test_kml_is_split_into_one_layer_per_geometry_type(self):
        group = self._import(_kml_upload())

        self.assertEqual(group.source_format, LayerGroup.SourceFormat.KML)
        self.assertEqual(group.source_filename, "sample.kml")
        layers = self._layers_by_type(group)
        self.assertEqual(
            {t: layer.feature_count for t, layer in layers.items()},
            {"MultiPoint": 2, "MultiLineString": 3, "MultiPolygon": 3},
        )
        self.assertEqual(layers["MultiPoint"].name, "Survey – Points")
        for layer in layers.values():
            self.assertEqual(layer.owner, self.owner)
            self.assertEqual(layer.srid, 4326)
            self.assertIsNotNone(layer.bounds)
        # Nothing left behind but the three layer tables (staging dropped).
        self.assertEqual(_layers_data_tables() - self.tables_before, {l.table_name for l in layers.values()})

    def test_attributes_keep_kml_fields_and_drop_rendering_flags_and_empty_columns(self):
        layers = self._layers_by_type(self._import(_kml_upload()))
        points = _columns(layers["MultiPoint"].table_name)
        self.assertTrue({"id", "geom", "name", "description", "kind", "kml_folder", "kml_color"} <= points)
        self.assertFalse({"tessellate", "extrude", "visibility", "timestamp", "kml_style", "ogr_style"} & points)
        # 'kind' only exists on the point; all-null columns are dropped per table.
        self.assertNotIn("kind", _columns(layers["MultiLineString"].table_name))
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT name, kml_folder FROM layers_data."{layers["MultiPoint"].table_name}" ORDER BY id'
            )
            self.assertEqual(cursor.fetchall(), [("P1", 'Sites "A"'), ("Mixed", "Areas")])

    def test_kml_colours_are_stored_per_feature_and_seed_the_layer_style(self):
        layers = self._layers_by_type(self._import(_kml_upload()))

        self.assertEqual(
            layers["MultiLineString"].style,
            {"color": "#ff0000", "opacity": 1.0, "strokeWidth": 3.0, "useSourceColors": True},
        )
        self.assertEqual(layers["MultiPolygon"].style["color"], "#0000ff")
        self.assertEqual(layers["MultiPolygon"].style["strokeColor"], "#0000ff")
        self.assertEqual(layers["MultiPoint"].style["color"], "#00ff00")  # StyleMap "normal" pin

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT name, kml_color, kml_width FROM layers_data."{layers["MultiLineString"].table_name}" ORDER BY name'
            )
            rows = cursor.fetchall()
        self.assertEqual(rows[0], ("L1", "rgba(255,0,0,1.0)", 3.0))
        self.assertEqual(rows[2][0:2], ("Mixed", "rgba(255,165,0,1.0)"))

    def test_tiles_render_from_every_split_table(self):
        group = self._import(_kml_upload())
        with connection.cursor() as cursor:
            for layer in group.layers.all():
                cursor.execute(
                    "SELECT length(layers_data.geolayers_tile(0, 0, 0, json_build_object('layer', %s)))",
                    [layer.table_name],
                )
                self.assertGreater(cursor.fetchone()[0], 0, layer.geometry_type)

    def test_kmz_is_read_from_its_doc_kml(self):
        group = self._import(_kmz_upload())
        self.assertEqual(group.source_format, LayerGroup.SourceFormat.KMZ)
        self.assertEqual(group.layers.count(), 3)

    def test_single_geometry_type_still_makes_a_group(self):
        group = self._import(_kml_upload(LINES_ONLY_KML, "lines.kml"))
        self.assertEqual([l.geometry_type for l in group.layers.all()], ["MultiLineString"])
        self.assertNotIn("useSourceColors", group.layers.get().style)

    def test_file_without_features_fails_cleanly(self):
        with self.assertRaises(LayerImportError):
            self._import(_kml_upload(EMPTY_KML, "empty.kml"))
        self.assertFalse(LayerGroup.objects.exists())
        self.assertEqual(_layers_data_tables(), self.tables_before)

    def test_broken_kmz_is_rejected(self):
        with self.assertRaises(LayerImportError):
            self._import(SimpleUploadedFile("broken.kmz", b"not a zip"))
        with self.assertRaises(LayerImportError):
            self._import(SimpleUploadedFile("broken.kml", b"<not-kml"))
        self.assertFalse(LayerGroup.objects.exists())

    def test_upload_api_returns_the_group(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        res = client.post("/api/layers/", {"name": "Survey", "file": _kml_upload()}, format="multipart")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["group"]["layer_count"], 3)
        self.assertEqual(res.json()["group"]["feature_count"], 8)
        self.assertEqual(
            [l["geometry_type"] for l in res.json()["group"]["layers"]],
            ["MultiPolygon", "MultiLineString", "MultiPoint"],
        )

        bad = client.post("/api/layers/", {"name": "x", "file": SimpleUploadedFile("a.txt", b"x")}, format="multipart")
        self.assertEqual(bad.status_code, 400)


# --------------------------------------------------------------------------- groups (no GDAL needed)
def _make_group(owner, name="Survey"):
    """A group with real (tiny) point/line/polygon tables, built with SQL."""
    group = LayerGroup.objects.create(owner=owner, name=name, source_format=LayerGroup.SourceFormat.KML)
    specs = (
        ("MultiPoint", "ST_Multi(ST_MakePoint(46.7, 24.7))"),
        ("MultiLineString", "ST_Multi(ST_MakeLine(ST_MakePoint(46.7, 24.7), ST_MakePoint(46.8, 24.8)))"),
        ("MultiPolygon", "ST_Multi(ST_MakeEnvelope(46.6, 24.6, 46.7, 24.7))"),
    )
    with connection.cursor() as cursor:
        for geom_type, geom_sql in specs:
            table = f"layer_{uuid.uuid4().hex}"
            cursor.execute(
                f'CREATE TABLE layers_data."{table}" (id serial PRIMARY KEY, name text, '
                f"kml_color text, geom geometry({geom_type}, 4326))"
            )
            cursor.execute(
                f"INSERT INTO layers_data.\"{table}\" (name, kml_color, geom) "
                f"VALUES ('f', 'rgba(255,0,0,1)', ST_SetSRID({geom_sql}, 4326))"
            )
            LayerInfo.objects.create(
                owner=owner, group=group, name=f"{name} – {geom_type}", schema_name="layers_data",
                table_name=table, geometry_type=geom_type, feature_count=1,
            )
    return group


def _table_exists(table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [f"layers_data.{table}"])
        return cursor.fetchone()[0] is not None


class LayerGroupApiTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.owner = users.create_user("gowner", "gowner@example.com", "pw-12345!")
        self.viewer = users.create_user("gviewer", "gviewer@example.com", "pw-12345!")
        self.group = _make_group(self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_owner_lists_group_with_layers_in_stacking_order(self):
        res = self.client.get("/api/layer-groups/")
        self.assertEqual(res.status_code, 200)
        group = res.json()["results"][0]
        self.assertEqual(group["layer_count"], 3)
        self.assertEqual(group["my_permission"], "owner")
        self.assertEqual(
            [l["geometry_type"] for l in group["layers"]], ["MultiPolygon", "MultiLineString", "MultiPoint"]
        )
        layers = self.client.get(f"/api/layers/?group={self.group.id}").json()["results"]
        self.assertEqual(len(layers), 3)
        self.assertEqual(layers[0]["group_detail"]["id"], str(self.group.id))
        self.assertEqual(self.client.get("/api/layers/?group=not-a-uuid").json()["results"], [])

    def test_group_share_grants_every_layer_and_unshare_removes_them(self):
        res = self.client.post(
            f"/api/layer-groups/{self.group.id}/share/", {"shared_with": self.viewer.id, "permission": "view"}
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["layer_count"], 3)
        for layer in self.group.layers.all():
            self.assertTrue(user_can_view_layer(self.viewer, layer))

        viewer = APIClient()
        viewer.force_authenticate(self.viewer)
        listed = viewer.get("/api/layer-groups/").json()["results"]
        self.assertEqual([g["my_permission"] for g in listed], ["view"])
        self.assertEqual(viewer.delete(f"/api/layer-groups/{self.group.id}/").status_code, 403)
        self.assertEqual(viewer.patch(f"/api/layer-groups/{self.group.id}/", {"name": "x"}).status_code, 403)

        res = self.client.post(f"/api/layer-groups/{self.group.id}/unshare/", {"user_id": self.viewer.id})
        self.assertEqual(res.status_code, 204)
        self.assertFalse(LayerShare.objects.filter(shared_with=self.viewer).exists())

    def test_group_cannot_be_created_directly(self):
        self.assertEqual(self.client.post("/api/layer-groups/", {"name": "x"}).status_code, 405)

    def test_deleting_group_drops_all_its_tables(self):
        tables = list(self.group.layers.values_list("table_name", flat=True))
        res = self.client.delete(f"/api/layer-groups/{self.group.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(LayerGroup.objects.exists())
        self.assertFalse(LayerInfo.objects.exists())
        self.assertFalse(any(_table_exists(t) for t in tables))

    def test_group_goes_with_its_last_layer(self):
        layers = list(self.group.layers.all())
        for layer in layers[:-1]:
            delete_layer(layer)
        self.assertTrue(LayerGroup.objects.filter(pk=self.group.pk).exists())
        delete_layer(layers[-1])
        self.assertFalse(LayerGroup.objects.filter(pk=self.group.pk).exists())

    def test_add_group_to_map_stacks_polygons_lines_points(self):
        map_project = MapProject.objects.create(owner=self.owner, name="Map")
        res = self.client.post(f"/api/maps/{map_project.id}/layers/", {"group": str(self.group.id)}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        added = sorted(res.json(), key=lambda ml: ml["order"])
        self.assertEqual(
            [ml["layer_detail"]["geometry_type"] for ml in added],
            ["MultiPolygon", "MultiLineString", "MultiPoint"],
        )
        bad = self.client.post(
            f"/api/maps/{map_project.id}/layers/",
            {"group": str(self.group.id), "layer": str(added[0]["layer"])},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)

    def test_cannot_add_someone_elses_group_to_a_map(self):
        stranger_map = MapProject.objects.create(owner=self.viewer, name="Theirs")
        viewer = APIClient()
        viewer.force_authenticate(self.viewer)
        res = viewer.post(f"/api/maps/{stranger_map.id}/layers/", {"group": str(self.group.id)}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_source_colours_drive_shared_style_until_user_picks_one(self):
        line = self.group.layers.get(geometry_type="MultiLineString")
        line.style = {"color": "#ff0000", "opacity": 0.4, "strokeWidth": 3, "useSourceColors": True}
        paint = build_layer_paint_layers(layer=line, source_id="s")[0][0]["paint"]
        self.assertEqual(paint["line-color"], ["to-color", ["get", "kml_color"], "#ff0000"])
        self.assertEqual(paint["line-width"][0], "case")
        self.assertEqual(paint["line-opacity"], 1)

        line.style = {"color": "#00ff00", "opacity": 0.4, "strokeWidth": 3}
        paint = build_layer_paint_layers(layer=line, source_id="s")[0][0]["paint"]
        self.assertEqual(paint["line-color"], "#00ff00")
        self.assertEqual(paint["line-opacity"], 0.4)


class PaginationTests(TestCase):
    def test_page_size_query_param_is_honoured(self):
        owner = get_user_model().objects.create_user("many", "many@example.com", "pw-12345!")
        for i in range(30):
            LayerInfo.objects.create(owner=owner, name=f"L{i}", schema_name="layers_data", table_name=f"layer_{i:032x}")
        client = APIClient()
        client.force_authenticate(owner)
        self.assertEqual(len(client.get("/api/layers/").json()["results"]), 25)
        self.assertEqual(len(client.get("/api/layers/?page_size=500").json()["results"]), 30)
