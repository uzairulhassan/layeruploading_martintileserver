"""KML / KMZ -> one LayerGroup with up to three PostGIS tables (points, lines, polygons).

A KML document mixes geometry types and folders, but each ``LayerInfo`` table
(and so each ``geolayers_tile`` layer) holds one geometry family. The import:

1. loads every KML folder (OGR layer) into one staging table with ogr2ogr. The
   LIBKML driver resolves each Placemark's style into ``kml_style``; heights are
   dropped (``-dim XY``) and the folder name is kept in ``kml_folder``.
   MultiGeometry Placemarks stay one row (a GeometryCollection).
2. splits the staging table with ``ST_CollectionExtract`` into one
   ``layer_<hex>`` table per family present. A mixed MultiGeometry contributes
   its point, line and polygon parts to each table, still as one feature each.
3. stores each feature's own KML colours in ``kml_color`` / ``kml_stroke`` /
   ``kml_width``, and seeds each layer's ``style`` from its most common style
   (see ``kml_style``) so users can still restyle it.

Steps 2-3 run in one transaction, so a failure leaves no half-built layers.
"""
from __future__ import annotations

import tempfile
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.gis.gdal import DataSource, GDALException
from django.db import connection, transaction

from . import kml_style
from .models import LayerGroup, LayerInfo
from .services import (
    LayerImportError,
    _drop_table,
    _ensure_schema_exists,
    _ensure_spatial_index,
    _generate_table_name,
    _introspect_table,
    _pg_connection_string,
    run_ogr2ogr,
)

KML_EXTENSIONS = {
    ".kml": LayerGroup.SourceFormat.KML,
    ".kmz": LayerGroup.SourceFormat.KMZ,
}

# (family, ST_CollectionExtract type, PostGIS type, LayerInfo name suffix)
FAMILIES = (
    (kml_style.POINT, 1, "MultiPoint", "Points"),
    (kml_style.LINE, 2, "MultiLineString", "Lines"),
    (kml_style.POLYGON, 3, "MultiPolygon", "Polygons"),
)

# KML rendering flags LIBKML exposes as fields; meaningless once the data is in PostGIS.
_DROPPED_COLUMNS = {"altitudemode", "tessellate", "extrude", "visibility", "draworder", "icon"}
_INTERNAL_COLUMNS = {"ogc_fid", "geom", "ogr_style", "kml_style", "kml_color", "kml_stroke", "kml_width"}


def is_kml_upload(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in KML_EXTENSIONS


def _q(identifier: str) -> str:
    """Quote a PostgreSQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _check_kmz(path: Path):
    if not zipfile.is_zipfile(path):
        raise LayerImportError("This .kmz file is not a valid KMZ (zip) archive.")
    with zipfile.ZipFile(path) as zf:
        if not any(name.lower().endswith(".kml") for name in zf.namelist()):
            raise LayerImportError("This .kmz archive does not contain a .kml document.")


def _kml_layer_names(path: Path) -> list[str]:
    try:
        source = DataSource(str(path))
    except GDALException as exc:
        raise LayerImportError("Could not read this KML/KMZ file. Is it valid KML?") from exc
    return [layer.name for layer in source]


def _load_staging(path: Path, layer_names: list[str], schema: str, staging: str):
    """Append every KML folder into one staging table (first folder creates it)."""
    for index, layer_name in enumerate(layer_names):
        sql = (
            f"SELECT *, OGR_STYLE AS kml_style, {_sqlite_literal(layer_name)} AS kml_folder "
            f"FROM {_q(layer_name)}"
        )
        cmd = [
            settings.OGR2OGR_PATH,
            "-f", "PostgreSQL",
            _pg_connection_string(),
            str(path),
            "-dialect", "SQLite",
            "-sql", sql,
            "-nln", f"{schema}.{staging}",
            "-nlt", "GEOMETRY",
            "-dim", "XY",
            "-t_srs", "EPSG:4326",
            "--config", "LIBKML_RESOLVE_STYLE", "YES",
            "--config", "PG_USE_COPY", "YES",
        ]
        if index == 0:
            cmd += ["-lco", "GEOMETRY_NAME=geom", "-lco", "FID=ogc_fid", "-lco", "PRECISION=NO"]
        else:
            cmd += ["-append", "-addfields"]
        run_ogr2ogr(cmd)


def _table_columns(cursor, schema: str, table: str) -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        [schema, table],
    )
    return [row[0] for row in cursor.fetchall()]


def _family_counts(cursor, schema: str, staging: str) -> dict[str, int]:
    filters = ", ".join(
        f"COUNT(*) FILTER (WHERE NOT ST_IsEmpty(ST_CollectionExtract(geom, {extract})))"
        for _, extract, _, _ in FAMILIES
    )
    cursor.execute(f"SELECT {filters} FROM {_q(schema)}.{_q(staging)} WHERE geom IS NOT NULL")
    row = cursor.fetchone()
    return {family: row[i] for i, (family, _, _, _) in enumerate(FAMILIES)}


def _create_family_table(cursor, *, schema, staging, table, family, extract, pg_type, attributes, has_style):
    """Create ``schema.table`` holding the ``family`` parts of every staged feature."""
    select_attrs = "".join(
        f", s.{_q(col)} AS {_q('kml_id' if col == 'id' else col)}" for col in attributes
    )
    style_expr = "s.kml_style" if has_style else "NULL::text"
    cursor.execute(
        f"""
        CREATE TABLE {_q(schema)}.{_q(table)} AS
        SELECT (row_number() OVER (ORDER BY s.ogc_fid))::integer AS id{select_attrs},
               {style_expr} AS kml_style_src,
               ST_Multi(s._geolayers_part)::geometry({pg_type}, 4326) AS geom
        FROM (
            SELECT *, ST_CollectionExtract(geom, {extract}) AS _geolayers_part
            FROM {_q(schema)}.{_q(staging)}
            WHERE geom IS NOT NULL
        ) s
        WHERE NOT ST_IsEmpty(s._geolayers_part)
        """
    )
    cursor.execute(
        f"ALTER TABLE {_q(schema)}.{_q(table)} ADD PRIMARY KEY (id), "
        "ADD COLUMN kml_color text, ADD COLUMN kml_stroke text, ADD COLUMN kml_width double precision"
    )


def _apply_kml_colors(cursor, *, schema, table, family) -> tuple[str | None, bool]:
    """Fill the per-feature colour columns. Returns ``(dominant style, any colours?)``."""
    cursor.execute(
        f"SELECT kml_style_src, COUNT(*) FROM {_q(schema)}.{_q(table)} "
        "WHERE kml_style_src IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1"
    )
    styles, colors, strokes, widths = [], [], [], []
    dominant = None
    for style, _count in cursor.fetchall():
        values = kml_style.feature_columns(style, family)
        if not any(v is not None for v in values.values()):
            continue
        if dominant is None and values["kml_color"]:
            dominant = style
        styles.append(style)
        colors.append(values["kml_color"])
        strokes.append(values["kml_stroke"])
        widths.append(values["kml_width"])

    if styles:
        cursor.execute(
            f"""
            UPDATE {_q(schema)}.{_q(table)} t
            SET kml_color = m.color, kml_stroke = m.stroke, kml_width = m.width
            FROM unnest(%s::text[], %s::text[], %s::text[], %s::float8[]) AS m(style, color, stroke, width)
            WHERE t.kml_style_src = m.style
            """,
            [styles, colors, strokes, widths],
        )
    cursor.execute(f"ALTER TABLE {_q(schema)}.{_q(table)} DROP COLUMN kml_style_src")
    return dominant, any(c is not None for c in colors)


def _drop_empty_columns(cursor, *, schema, table):
    """KML exposes many optional fields (timestamp, begin, end, …); drop the all-null ones."""
    columns = [c for c in _table_columns(cursor, schema, table) if c not in ("id", "geom")]
    if not columns:
        return
    cursor.execute(
        f"SELECT {', '.join(f'COUNT({_q(c)})' for c in columns)} FROM {_q(schema)}.{_q(table)}"
    )
    counts = cursor.fetchone()
    empty = [col for col, count in zip(columns, counts) if count == 0]
    if empty:
        drops = ", ".join(f"DROP COLUMN {_q(col)}" for col in empty)
        cursor.execute(f"ALTER TABLE {_q(schema)}.{_q(table)} {drops}")


def _layer_name(group_name: str, suffix: str) -> str:
    tail = f" – {suffix}"
    max_len = LayerInfo._meta.get_field("name").max_length
    return group_name[: max_len - len(tail)] + tail


def import_kml(*, owner, name: str, description: str, uploaded_file) -> LayerGroup:
    """Import a .kml/.kmz upload as a LayerGroup with one LayerInfo per geometry family."""
    filename = getattr(uploaded_file, "name", "") or ""
    extension = Path(filename).suffix.lower()
    if extension not in KML_EXTENSIONS:
        raise LayerImportError("Upload a .kml or .kmz file.")

    schema = settings.LAYER_TABLE_SCHEMA
    staging = f"_kml_staging_{uuid.uuid4().hex}"
    _ensure_schema_exists(schema)

    with tempfile.TemporaryDirectory(prefix="kml_upload_") as tmp:
        path = Path(tmp) / f"upload{extension}"
        with open(path, "wb") as fh:
            for chunk in uploaded_file.chunks():
                fh.write(chunk)
        if extension == ".kmz":
            _check_kmz(path)

        layer_names = _kml_layer_names(path)
        if not layer_names:
            raise LayerImportError("No folders or placemarks found in this file.")

        try:
            _load_staging(path, layer_names, schema, staging)
            return _build_group(
                owner=owner,
                name=name,
                description=description,
                filename=filename,
                source_format=KML_EXTENSIONS[extension],
                schema=schema,
                staging=staging,
            )
        finally:
            _drop_table(schema, staging)


def _build_group(*, owner, name, description, filename, source_format, schema, staging) -> LayerGroup:
    with transaction.atomic():
        with connection.cursor() as cursor:
            staged_columns = _table_columns(cursor, schema, staging)
            if not staged_columns:
                raise LayerImportError("No points, lines or polygons found in this file.")
            counts = _family_counts(cursor, schema, staging)
            if not any(counts.values()):
                raise LayerImportError("No points, lines or polygons found in this file.")
            attributes = [
                c for c in staged_columns
                if c not in _INTERNAL_COLUMNS and c not in _DROPPED_COLUMNS
            ]
            has_style = "kml_style" in staged_columns

            group = LayerGroup.objects.create(
                owner=owner,
                name=name,
                description=description,
                source_format=source_format,
                source_filename=filename,
            )
            for family, extract, pg_type, suffix in FAMILIES:
                if not counts[family]:
                    continue
                table = _generate_table_name()
                _create_family_table(
                    cursor,
                    schema=schema,
                    staging=staging,
                    table=table,
                    family=family,
                    extract=extract,
                    pg_type=pg_type,
                    attributes=attributes,
                    has_style=has_style,
                )
                dominant, has_colors = _apply_kml_colors(cursor, schema=schema, table=table, family=family)
                _drop_empty_columns(cursor, schema=schema, table=table)
                _ensure_spatial_index(schema, table)
                LayerInfo.objects.create(
                    owner=owner,
                    group=group,
                    name=_layer_name(name, suffix),
                    description=description,
                    schema_name=schema,
                    table_name=table,
                    source_filename=filename,
                    style=kml_style.layer_style(dominant, family, use_source_colors=has_colors),
                    **_introspect_table(schema, table),
                )
    return group
