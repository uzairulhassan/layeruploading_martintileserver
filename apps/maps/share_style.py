"""Build a Mapbox Style Spec for an externally shared map composition.

Tiles stay raw MVT per layer; this document mirrors the map builder: basemap
(free OSM so MapLibre clients need no Mapbox token), viewport, layer order,
visibility, opacity and style overrides. Style is read live from the map so
edits propagate without recreating the share link.
"""
from __future__ import annotations

from collections.abc import Callable

from apps.layers.share_style import MAPLIBRE_GLYPHS, build_layer_paint_layers

from .models import MapProject

_OSM_SOURCE_ID = "basemap-osm"
_OSM_LAYER_ID = "basemap-osm-raster"
_OSM_TILES = [
    "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
]


def build_map_share_style(
    *,
    map_project: MapProject,
    tiles_url_for_table: Callable[[str], str],
) -> dict:
    """Return a Mapbox Style Spec v8 document for ``map_project``.

    ``tiles_url_for_table(table_name)`` must return an absolute XYZ template
    ``…/m/<token>/<table>/{z}/{x}/{y}.pbf`` for this share token.
    """
    sources: dict = {
        _OSM_SOURCE_ID: {
            "type": "raster",
            "tiles": list(_OSM_TILES),
            "tileSize": 256,
            "attribution": "&copy; OpenStreetMap contributors",
        }
    }
    layers: list[dict] = [
        {
            "id": _OSM_LAYER_ID,
            "type": "raster",
            "source": _OSM_SOURCE_ID,
            "layout": {"visibility": "visible"},
        }
    ]

    needs_glyphs = False
    layer_meta: list[dict] = []

    map_layers = (
        map_project.map_layers.select_related("layer").order_by("order")
    )
    for map_layer in map_layers:
        layer = map_layer.layer
        table = layer.table_name
        source_id = f"src-{table}"
        sources[source_id] = {
            "type": "vector",
            "tiles": [tiles_url_for_table(table)],
            "minzoom": 0,
            "maxzoom": 22,
        }
        visibility = "visible" if map_layer.visible else "none"
        override = map_layer.style_override or {}
        paint_layers, layer_needs_glyphs = build_layer_paint_layers(
            layer=layer,
            source_id=source_id,
            style=override,
            opacity=map_layer.opacity,
            visibility=visibility,
        )
        layers.extend(paint_layers)
        needs_glyphs = needs_glyphs or layer_needs_glyphs
        layer_meta.append(
            {
                "id": str(layer.id),
                "name": layer.name,
                "table": table,
                "order": map_layer.order,
                "visible": map_layer.visible,
                "opacity": map_layer.opacity,
            }
        )

    doc: dict = {
        "version": 8,
        "name": map_project.name,
        "center": [map_project.center_lng, map_project.center_lat],
        "zoom": map_project.zoom,
        "metadata": {
            "geolayers:kind": "map",
            "geolayers:map_id": str(map_project.id),
            "geolayers:basemap_style": map_project.basemap_style,
            "geolayers:layers": layer_meta,
        },
        "sources": sources,
        "layers": layers,
    }
    if needs_glyphs:
        doc["glyphs"] = MAPLIBRE_GLYPHS
    return doc
