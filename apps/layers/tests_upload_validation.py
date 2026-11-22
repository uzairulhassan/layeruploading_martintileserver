"""Early layer-upload format checks."""
from io import BytesIO
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import serializers

from .upload_validation import validate_layer_upload_file


def _zip_bytes(names_to_bytes: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in names_to_bytes.items():
            zf.writestr(name, data)
    return buf.getvalue()


@override_settings(MAX_SHAPEFILE_UPLOAD_SIZE=5 * 1024 * 1024)
class UploadValidationTests(SimpleTestCase):
    def test_rejects_wrong_extension(self):
        upload = SimpleUploadedFile("roads.geojson", b'{"type":"FeatureCollection"}')
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)

    def test_rejects_empty_file(self):
        upload = SimpleUploadedFile("roads.kml", b"")
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)

    def test_rejects_non_zip_with_zip_extension(self):
        upload = SimpleUploadedFile("roads.zip", b"not-a-zip")
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)

    def test_rejects_zip_without_shapefile(self):
        raw = _zip_bytes({"readme.txt": b"hello"})
        upload = SimpleUploadedFile("roads.zip", raw)
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)

    def test_accepts_shapefile_zip(self):
        raw = _zip_bytes({
            "roads.shp": b"shp",
            "roads.shx": b"shx",
            "roads.dbf": b"dbf",
            "roads.prj": b"prj",
        })
        upload = SimpleUploadedFile("roads.zip", raw)
        self.assertIs(validate_layer_upload_file(upload), upload)

    def test_rejects_fake_kml(self):
        upload = SimpleUploadedFile("roads.kml", b"hello world")
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)

    def test_accepts_simple_kml(self):
        upload = SimpleUploadedFile(
            "roads.kml",
            b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"></kml>',
        )
        self.assertIs(validate_layer_upload_file(upload), upload)

    def test_rejects_kmz_without_kml(self):
        raw = _zip_bytes({"notes.txt": b"nope"})
        upload = SimpleUploadedFile("roads.kmz", raw)
        with self.assertRaises(serializers.ValidationError):
            validate_layer_upload_file(upload)
