"""Unit tests for shapefile zip extract safety and LayerInfo → PostGIS cleanup."""
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from .models import LayerInfo
from .services import LayerImportError, _extract_shapefile, _safe_zip_member_name


class SafeZipMemberNameTests(TestCase):
    def test_accepts_nested_and_flat_names(self):
        self.assertEqual(_safe_zip_member_name("roads/roads.shp"), "roads.shp")
        self.assertEqual(_safe_zip_member_name("roads.shp"), "roads.shp")

    def test_rejects_traversal_and_absolute(self):
        for name in ("../evil.shp", "foo/../../evil.shp", "/tmp/evil.shp", "..", "", "dir/"):
            with self.assertRaises(LayerImportError):
                _safe_zip_member_name(name)


class ExtractShapefileTests(TestCase):
    def _write_zip(self, dest: Path, entries: dict[str, bytes]) -> Path:
        zip_path = dest / "upload.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return zip_path

    def test_extracts_nested_shapefile_by_basename_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._write_zip(
                root,
                {
                    "folder/demo.shp": b"shp",
                    "folder/demo.shx": b"shx",
                    "folder/demo.dbf": b"dbf",
                    "folder/demo.prj": b"prj",
                },
            )
            out = root / "out"
            out.mkdir()
            shp = _extract_shapefile(zip_path, out)
            self.assertEqual(shp.name, "demo.shp")
            self.assertEqual(shp.parent, out)
            self.assertTrue((out / "demo.shx").is_file())

    def test_zip_slip_paths_are_rejected_before_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._write_zip(root, {"../../evil.shp": b"nope", "demo.shx": b"x", "demo.dbf": b"x"})
            out = root / "out"
            out.mkdir()
            with self.assertRaises(LayerImportError):
                _extract_shapefile(zip_path, out)
            self.assertFalse((root / "evil.shp").exists())


@skipUnless(connection.vendor == "postgresql", "needs PostGIS to create/drop layer tables")
class LayerTableCleanupSignalTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("cleanup", "cleanup@example.com", "pw-12345!")
        self.table = "layer_" + "e" * 32
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS layers_data")
            cursor.execute(
                f'CREATE TABLE layers_data."{self.table}" (id serial PRIMARY KEY, '
                "geom geometry(Point, 4326))"
            )
        self.layer = LayerInfo.objects.create(
            owner=self.owner,
            name="Cleanup",
            schema_name="layers_data",
            table_name=self.table,
        )

    def _table_exists(self) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", [f"layers_data.{self.table}"])
            return cursor.fetchone()[0] is not None

    def test_orm_delete_drops_postgis_table(self):
        self.assertTrue(self._table_exists())
        self.layer.delete()
        self.assertFalse(LayerInfo.objects.filter(pk=self.layer.pk).exists())
        self.assertFalse(self._table_exists())

    def test_cascading_user_delete_drops_postgis_table(self):
        self.assertTrue(self._table_exists())
        self.owner.delete()
        self.assertFalse(LayerInfo.objects.filter(table_name=self.table).exists())
        self.assertFalse(self._table_exists())
