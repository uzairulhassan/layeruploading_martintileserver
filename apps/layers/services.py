"""Shapefile -> dynamic PostGIS table import pipeline.

Uploaded shapefiles (as a .zip containing .shp/.shx/.dbf/.prj) are imported
with ogr2ogr into a brand-new, uniquely-named table in the ``LAYER_TABLE_SCHEMA``
schema. Martin auto-discovers any spatial table in the database and serves it
as vector tiles, so no further wiring is required once the table exists.
"""
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from .models import LayerInfo

REQUIRED_SHAPEFILE_EXTENSIONS = {".shp", ".shx", ".dbf"}

_GEOMETRY_TYPE_MAP = {
    "POINT": LayerInfo.GeometryType.POINT,
    "MULTIPOINT": LayerInfo.GeometryType.MULTIPOINT,
    "LINESTRING": LayerInfo.GeometryType.LINESTRING,
    "MULTILINESTRING": LayerInfo.GeometryType.MULTILINESTRING,
    "POLYGON": LayerInfo.GeometryType.POLYGON,
    "MULTIPOLYGON": LayerInfo.GeometryType.MULTIPOLYGON,
}


class ShapefileImportError(Exception):
    """Raised for any user-correctable failure in the import pipeline."""


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


def _extract_shapefile(zip_path: Path, dest_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            target = dest_dir / Path(name).name
            if not str(target.resolve()).startswith(str(dest_dir.resolve())):
                raise ShapefileImportError("Unsafe path found inside archive.")
        zf.extractall(dest_dir)

    shp_files = list(dest_dir.rglob("*.shp"))
    if not shp_files:
        raise ShapefileImportError("Archive does not contain a .shp file.")
    if len(shp_files) > 1:
        raise ShapefileImportError("Archive must contain exactly one shapefile.")

    shp_path = shp_files[0]
    stem = shp_path.stem
    present = {p.suffix.lower() for p in dest_dir.rglob(f"{stem}.*")}
    missing = REQUIRED_SHAPEFILE_EXTENSIONS - present
    if missing:
        raise ShapefileImportError(f"Shapefile is missing required files: {', '.join(sorted(missing))}")
    return shp_path


def _generate_table_name() -> str:
    return f"layer_{uuid.uuid4().hex}"


def _ensure_schema_exists(schema_name: str):
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')


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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        raise ShapefileImportError(
            f"ogr2ogr executable not found at '{settings.OGR2OGR_PATH}'. Is GDAL installed?"
        ) from exc
    if result.returncode != 0:
        raise ShapefileImportError(f"ogr2ogr failed: {result.stderr.strip() or result.stdout.strip()}")


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


def _drop_table(schema_name: str, table_name: str):
    with connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS "{schema_name}"."{table_name}" CASCADE')


def import_shapefile(*, owner, name: str, description: str, uploaded_file, default_style: dict | None = None) -> LayerInfo:
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
                style=default_style or {},
                **metadata,
            )
    except Exception:
        _drop_table(schema_name, table_name)
        raise

    return layer


def delete_layer(layer: LayerInfo):
    _drop_table(layer.schema_name, layer.table_name)
    layer.delete()
