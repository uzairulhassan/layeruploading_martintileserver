"""Shared PostGIS import helpers for shapefile and KML/KMZ uploads.

Shapefile (.zip with .shp/.shx/.dbf/.prj) import lives here. KML/KMZ splitting
lives in ``kml_import`` and reuses these helpers (ogr2ogr runner, table naming,
introspection, table drop). Layer row deletes drop tables via the ``LayerInfo``
``pre_delete`` signal (see ``signals``). Every imported table sits in
``LAYER_TABLE_SCHEMA`` (default ``layers_data``) and is served by Martin via
``layers_data.geolayers_tile(?layer=<table>)`` with no catalog reload.
"""
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from .models import LayerGroup, LayerInfo

REQUIRED_SHAPEFILE_EXTENSIONS = {".shp", ".shx", ".dbf"}

_GEOMETRY_TYPE_MAP = {
    "POINT": LayerInfo.GeometryType.POINT,
    "MULTIPOINT": LayerInfo.GeometryType.MULTIPOINT,
    "LINESTRING": LayerInfo.GeometryType.LINESTRING,
    "MULTILINESTRING": LayerInfo.GeometryType.MULTILINESTRING,
    "POLYGON": LayerInfo.GeometryType.POLYGON,
    "MULTIPOLYGON": LayerInfo.GeometryType.MULTIPOLYGON,
}


class LayerImportError(Exception):
    """Raised for any user-correctable failure in an import pipeline (shapefile or KML)."""


def _pg_connection_string() -> str:
    db = settings.DATABASES["default"]
    parts = [
        f"dbname='{db['NAME']}'",
        f"host='{db.get('HOST') or 'localhost'}'",
        f"port='{db.get('PORT') or 5432}'",
        f"user='{db['USER']}'",
        f"password='{db['PASSWORD']}'",
    ]
    return "PG:" + " ".join(parts)


def _safe_zip_member_name(name: str) -> str:
    """Return a flat basename for a zip entry, or raise if the path looks hostile."""
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        raise LayerImportError("Unsafe path found inside archive.")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise LayerImportError("Unsafe path found inside archive.")
    basename = Path(normalized).name
    if not basename or basename in {".", ".."}:
        raise LayerImportError("Unsafe path found inside archive.")
    return basename


def _extract_shapefile(zip_path: Path, dest_dir: Path) -> Path:
    """Extract shapefile sidecars into ``dest_dir`` using basenames only (no zip-slip)."""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Basename-only write: archive paths cannot escape ``dest_dir``.
            target = dest_dir / _safe_zip_member_name(info.filename)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    shp_files = list(dest_dir.glob("*.shp"))
    if not shp_files:
        raise LayerImportError("Archive does not contain a .shp file.")
    if len(shp_files) > 1:
        raise LayerImportError("Archive must contain exactly one shapefile.")

    shp_path = shp_files[0]
    stem = shp_path.stem
    present = {p.suffix.lower() for p in dest_dir.glob(f"{stem}.*")}
    missing = REQUIRED_SHAPEFILE_EXTENSIONS - present
    if missing:
        raise LayerImportError(f"Shapefile is missing required files: {', '.join(sorted(missing))}")
    return shp_path


def _generate_table_name() -> str:
    return f"layer_{uuid.uuid4().hex}"


def _ensure_schema_exists(schema_name: str):
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')


def _ensure_spatial_index(schema_name: str, table_name: str):
    """GIST index speeds Martin tile queries on large layers."""
    index_name = f"{table_name}_geom_idx"
    with connection.cursor() as cursor:
        cursor.execute(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{schema_name}"."{table_name}" USING GIST (geom)'
        )
        cursor.execute(f'ANALYZE "{schema_name}"."{table_name}"')


def _run_ogr2ogr(shp_path: Path, schema_name: str, table_name: str):
    cmd = [
        settings.OGR2OGR_PATH,
        "-f", "PostgreSQL",
        _pg_connection_string(),
        str(shp_path),
        "-nln", f"{schema_name}.{table_name}",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=id",
        "-lco", "PRECISION=NO",
        "-t_srs", "EPSG:4326",
        "-nlt", "PROMOTE_TO_MULTI",
        "-overwrite",
    ]
    run_ogr2ogr(cmd)


def run_ogr2ogr(cmd: list[str]):
    """Run one ogr2ogr command; failures become a user-facing ``LayerImportError``."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        raise LayerImportError(
            f"ogr2ogr executable not found at '{settings.OGR2OGR_PATH}'. Is GDAL installed?"
        ) from exc
    if result.returncode != 0:
        raise LayerImportError(f"ogr2ogr failed: {result.stderr.strip() or result.stdout.strip()}")


def _introspect_table(schema_name: str, table_name: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT type, srid FROM geometry_columns WHERE f_table_schema = %s AND f_table_name = %s",
            [schema_name, table_name],
        )
        row = cursor.fetchone()
        raw_geometry_type, srid = (row[0], row[1]) if row else ("GEOMETRY", 4326)

        cursor.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
        feature_count = cursor.fetchone()[0]

        bounds = None
        if feature_count:
            cursor.execute(
                f'SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) '
                f'FROM (SELECT ST_Extent(geom) AS e FROM "{schema_name}"."{table_name}") s'
            )
            extent_row = cursor.fetchone()
            if extent_row and extent_row[0] is not None:
                bounds = [round(v, 6) for v in extent_row]

        cursor.execute(
            """
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
              AND column_name NOT IN ('id', 'geom')
            ORDER BY ordinal_position
            """,
            [schema_name, table_name],
        )
        attribute_schema = [{"name": r[0], "type": r[1]} for r in cursor.fetchall()]

    return {
        "geometry_type": _GEOMETRY_TYPE_MAP.get((raw_geometry_type or "").upper(), LayerInfo.GeometryType.GEOMETRY),
        "srid": srid or 4326,
        "feature_count": feature_count,
        "bounds": bounds,
        "attribute_schema": attribute_schema,
    }


def drop_layer_table(schema_name: str, table_name: str):
    """Drop a PostGIS layer (or staging) table if it exists."""
    with connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS "{schema_name}"."{table_name}" CASCADE')


def import_shapefile(*, owner, name: str, description: str, uploaded_file) -> LayerInfo:
    """Extracts an uploaded .zip shapefile and imports it into a new PostGIS table."""
    schema_name = settings.LAYER_TABLE_SCHEMA
    table_name = _generate_table_name()

    with tempfile.TemporaryDirectory(prefix="shp_upload_") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "upload.zip"
        with open(zip_path, "wb") as fh:
            for chunk in uploaded_file.chunks():
                fh.write(chunk)

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        shp_path = _extract_shapefile(zip_path, extract_dir)

        _ensure_schema_exists(schema_name)
        _run_ogr2ogr(shp_path, schema_name, table_name)
        _ensure_spatial_index(schema_name, table_name)

    try:
        metadata = _introspect_table(schema_name, table_name)
        with transaction.atomic():
            layer = LayerInfo.objects.create(
                owner=owner,
                name=name,
                description=description,
                schema_name=schema_name,
                table_name=table_name,
                source_filename=getattr(uploaded_file, "name", ""),
                style={},
                **metadata,
            )
    except Exception:
        drop_layer_table(schema_name, table_name)
        raise

    return layer


def delete_layer(layer: LayerInfo):
    """Delete the layer row (signal drops its table). Empty KML groups go too."""
    group_id = layer.group_id
    with transaction.atomic():
        layer.delete()
        if group_id and not LayerInfo.objects.filter(group_id=group_id).exists():
            LayerGroup.objects.filter(pk=group_id).delete()


def delete_layer_group(group: LayerGroup):
    """Delete a KML/KMZ group; cascaded layers drop their tables via signal."""
    group.delete()


def sample_attribute_value(layer: LayerInfo, field_name: str) -> str | None:
    """Return one non-empty sample value from ``field_name`` for style previews.

    ``field_name`` must appear in the layer's recorded ``attribute_schema`` so
    identifiers are never taken from untrusted input alone.
    """
    allowed = {col.get("name") for col in (layer.attribute_schema or []) if col.get("name")}
    if field_name not in allowed:
        raise ValueError(f"Unknown attribute field: {field_name}")

    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            SELECT "{field_name}"::text
            FROM "{layer.schema_name}"."{layer.table_name}"
            WHERE "{field_name}" IS NOT NULL
              AND btrim("{field_name}"::text) <> ''
            LIMIT 1
            '''
        )
        row = cursor.fetchone()
    if not row or row[0] is None:
        return None
    text = str(row[0]).strip()
    return text or None
