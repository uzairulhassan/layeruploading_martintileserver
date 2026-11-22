"""Early validation for layer uploads (.zip shapefile, .kml, .kmz)."""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from rest_framework import serializers

UPLOAD_EXTENSIONS = (".zip", ".kml", ".kmz")

_ZIP_HEADERS = (b"PK\x03\x04", b"PK\x05\x06")
_REQUIRED_SHAPE_SIDECARS = (".shp", ".shx", ".dbf")


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _archive_basenames(uploaded_file) -> list[str]:
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    try:
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            return [
                Path(info.filename.replace("\\", "/")).name.lower()
                for info in zf.infolist()
                if not info.is_dir()
            ]
    except zipfile.BadZipFile as exc:
        raise serializers.ValidationError("This file is not a valid ZIP archive.") from exc


def validate_layer_upload_file(uploaded_file):
    """Reject wrong extensions, empty/oversized files, and obvious content mismatches."""
    filename = Path(getattr(uploaded_file, "name", "") or "").name
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise serializers.ValidationError("Choose a valid file to upload.")

    ext = _extension(filename)
    if ext not in UPLOAD_EXTENSIONS:
        raise serializers.ValidationError(
            "Use a .zip shapefile package, or a .kml / .kmz file."
        )

    size = getattr(uploaded_file, "size", None)
    max_bytes = settings.MAX_SHAPEFILE_UPLOAD_SIZE
    if size is not None and size <= 0:
        raise serializers.ValidationError("The selected file is empty.")
    if size is not None and size > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise serializers.ValidationError(f"File exceeds the {max_mb}MB upload limit.")

    head = uploaded_file.read(8)
    uploaded_file.seek(0)
    if not head:
        raise serializers.ValidationError("The selected file is empty.")

    if ext in {".zip", ".kmz"}:
        if not head.startswith(_ZIP_HEADERS):
            kind = "ZIP shapefile package" if ext == ".zip" else "KMZ archive"
            raise serializers.ValidationError(f"This does not look like a valid {kind}.")
        names = _archive_basenames(uploaded_file)
        if not names:
            raise serializers.ValidationError("This archive is empty.")
        if ext == ".zip":
            present = {f".{name.rsplit('.', 1)[-1]}" for name in names if "." in name}
            if any(sfx not in present for sfx in _REQUIRED_SHAPE_SIDECARS):
                raise serializers.ValidationError(
                    "This ZIP must contain a shapefile (.shp, .shx, and .dbf)."
                )
            if sum(1 for name in names if name.endswith(".shp")) != 1:
                raise serializers.ValidationError(
                    "This ZIP must contain exactly one shapefile (.shp)."
                )
        elif not any(name.endswith(".kml") for name in names):
            raise serializers.ValidationError(
                "This KMZ archive must contain a .kml document."
            )

    if ext == ".kml":
        sample = uploaded_file.read(8192)
        uploaded_file.seek(0)
        text = sample.lstrip(b"\xef\xbb\xbf").lstrip()
        if text.startswith(b"PK"):
            raise serializers.ValidationError(
                "This looks like a ZIP/KMZ archive. Upload it as .kmz, or use a plain .kml file."
            )
        lowered = text[:4096].lower()
        if not text.startswith(b"<") or (b"kml" not in lowered and b"<?xml" not in lowered):
            raise serializers.ValidationError("This does not look like a valid KML file.")

    return uploaded_file
