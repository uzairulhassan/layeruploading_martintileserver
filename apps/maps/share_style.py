"""Build a Mapbox Style Spec for an externally shared map composition.

Tiles stay raw MVT per layer. Paint comes from ``build_layer_paint_layers``
(same source as the in-app map builder). Includes a free OSM basemap so
MapLibre clients need no Mapbox token, plus viewport, order, opacity and
style overrides. Only **visible** map layers are published. Style is read
live so edits propagate without recreating the share link.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

from apps.layers.share_style import (
    MAPLIBRE_GLYPHS,
    build_layer_paint_layers,
    build_style_legend,
    viewport_from_bounds,
)

from .models import MapProject

_OSM_SOURCE_ID = "basemap-osm"
_OSM_LAYER_ID = "basemap-osm-raster"
_OSM_TILES = [
    "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
]

# Matches GeoLayers "Create map" defaults (map_list.js).
_DEFAULT_CENTER_LNG = 0.0
_DEFAULT_CENTER_LAT = 0.0
_DEFAULT_ZOOM = 2.0


def _is_default_viewport(map_project: MapProject) -> bool:
    return (
        float(map_project.center_lng) == _DEFAULT_CENTER_LNG
        and float(map_project.center_lat) == _DEFAULT_CENTER_LAT
        and float(map_project.zoom) == _DEFAULT_ZOOM
    )


def _union_bounds(bounds_list: Iterable[object]) -> list[float] | None:
    """Union of ``[minx, miny, maxx, maxy]`` boxes in EPSG:4326."""
    boxes: list[tuple[float, float, float, float]] = []
    for raw in bounds_list:
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            continue
        try:
            minx, miny, maxx, maxy = (float(v) for v in raw)
        except (TypeError, ValueError):
            continue
        if maxx <= minx or maxy <= miny:
            continue
        boxes.append((minx, miny, maxx, maxy))
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def build_map_share_style(
    *,
    map_project: MapProject,
    tiles_url_for_table: Callable[[str], str],
) -> dict:
    """Return a Mapbox Style Spec v8 document for ``map_project``.

    ``tiles_url_for_table(table_name)`` must return an absolute XYZ template
    ``…/m/<token>/<table>/{z}/{x}/{y}.pbf`` for this share token.

    Only visible ``MapLayer`` rows are included. When layer bounds are known,
    ``metadata.geolayers:bounds`` is set; if the map still has the create-map
    default viewport, ``center`` / ``zoom`` are derived from that union.
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
    required_icons: list[str] = []
    layer_meta: list[dict] = []
    legend_sections: list[dict] = []
    bounds_parts: list[object] = []

    map_layers = (
        map_project.map_layers.filter(visible=True).select_related("layer").order_by("order")
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
        override = map_layer.style_override or {}
        merged_style = {**(layer.style or {}), **(override or {})}
        paint_layers, layer_needs_glyphs, layer_icons = build_layer_paint_layers(
            layer=layer,
            source_id=source_id,
            style=override,
            opacity=map_layer.opacity,
            visibility="visible",
        )
        layers.extend(paint_layers)
        needs_glyphs = needs_glyphs or layer_needs_glyphs
        for icon_id in layer_icons:
            if icon_id not in required_icons:
                required_icons.append(icon_id)
        label_config = layer.label_config or {}
        legend = build_style_legend(
            merged_style,
            title=layer.name,
            geometry_type=layer.geometry_type or "",
        )
        if legend:
            legend_sections.append(legend)
        if layer.bounds is not None:
            bounds_parts.append(layer.bounds)
        entry = {
            "id": str(layer.id),
            "name": layer.name,
            "table": table,
            "order": map_layer.order,
            "visible": True,
            "opacity": map_layer.opacity,
            "geometry_type": layer.geometry_type or "",
            "attribute_schema": layer.attribute_schema or [],
            "label_field": (label_config.get("field") or "").strip(),
        }
        if legend:
            entry["legend"] = legend
        layer_meta.append(entry)

    metadata: dict = {
        "geolayers:kind": "map",
        "geolayers:map_id": str(map_project.id),
        "geolayers:basemap_style": map_project.basemap_style,
        "geolayers:layers": layer_meta,
        "geolayers:required_icons": required_icons,
        "geolayers:legend": legend_sections,
    }

    doc: dict = {
        "version": 8,
        "name": map_project.name,
        "center": [map_project.center_lng, map_project.center_lat],
        "zoom": map_project.zoom,
        "metadata": metadata,
        "sources": sources,
        "layers": layers,
    }

    union = _union_bounds(bounds_parts)
    viewport = viewport_from_bounds(union) if union else None
    if viewport:
        metadata["geolayers:bounds"] = viewport["bounds"]
        if _is_default_viewport(map_project):
            doc["center"] = viewport["center"]
            doc["zoom"] = viewport["zoom"]

    if needs_glyphs:
        doc["glyphs"] = MAPLIBRE_GLYPHS
    return doc
