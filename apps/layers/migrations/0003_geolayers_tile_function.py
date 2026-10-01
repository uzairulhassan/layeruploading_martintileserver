# Creates layers_data.geolayers_tile() — the single Martin function source that
# serves every uploaded layer_<uuid> table as MVT via ?layer=<table>.

from django.db import migrations

GEOLAYERS_TILE_SQL = r"""
CREATE SCHEMA IF NOT EXISTS layers_data;

CREATE OR REPLACE FUNCTION layers_data.geolayers_tile(
    z integer,
    x integer,
    y integer,
    query_params json
) RETURNS bytea
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
AS $func$
DECLARE
    layer_name text;
    col_list   text;
    result     bytea;
BEGIN
    layer_name := query_params->>'layer';

    -- Only allow well-formed dynamic layer tables (blocks injection / system tables).
    IF layer_name IS NULL OR layer_name !~ '^layer_[0-9a-f]{32}$' THEN
        RETURN NULL;
    END IF;

    IF to_regclass(format('layers_data.%I', layer_name)) IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(
        string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum),
        ''
    )
    INTO col_list
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'layers_data'
      AND c.relname = layer_name
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname <> 'geom';

    IF col_list = '' THEN
        EXECUTE format(
            $sql$
            SELECT ST_AsMVT(tile, %L, 4096, 'geom')
            FROM (
                SELECT ST_AsMVTGeom(
                    ST_Transform(t.geom, 3857),
                    ST_TileEnvelope($1, $2, $3),
                    4096, 64, true
                ) AS geom
                FROM layers_data.%I t
                WHERE t.geom && ST_Transform(ST_TileEnvelope($1, $2, $3), 4326)
            ) AS tile
            WHERE tile.geom IS NOT NULL
            $sql$,
            layer_name, layer_name
        ) INTO result USING z, x, y;
    ELSE
        EXECUTE format(
            $sql$
            SELECT ST_AsMVT(tile, %L, 4096, 'geom')
            FROM (
                SELECT
                    ST_AsMVTGeom(
                        ST_Transform(t.geom, 3857),
                        ST_TileEnvelope($1, $2, $3),
                        4096, 64, true
                    ) AS geom,
                    %s
                FROM layers_data.%I t
                WHERE t.geom && ST_Transform(ST_TileEnvelope($1, $2, $3), 4326)
            ) AS tile
            WHERE tile.geom IS NOT NULL
            $sql$,
            layer_name, col_list, layer_name
        ) INTO result USING z, x, y;
    END IF;

    RETURN result;
END;
$func$;

GRANT USAGE ON SCHEMA layers_data TO martin_reader;
GRANT EXECUTE ON FUNCTION layers_data.geolayers_tile(integer, integer, integer, json) TO martin_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA layers_data TO martin_reader;
"""

GEOLAYERS_TILE_REVERSE = r"""
DROP FUNCTION IF EXISTS layers_data.geolayers_tile(integer, integer, integer, json);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0002_layersharelink_layersharelinkusage"),
    ]

    operations = [
        migrations.RunSQL(sql=GEOLAYERS_TILE_SQL, reverse_sql=GEOLAYERS_TILE_REVERSE),
    ]
