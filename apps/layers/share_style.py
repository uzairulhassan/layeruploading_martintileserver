"""Build Mapbox Style Spec paint/layout for GeoLayers layers.

Used by single-layer external share (``/x/<token>/style.json``) and by map
external share (``/m/<token>/style.json``) so both stay visually in sync with
the in-app map builder.
"""
from __future__ import annotations

from .geometry_hints import SUGGESTED_GEOMETRY
from .models import LayerInfo

# Free public glyphs so symbol (label) layers work without a Mapbox token.
MAPLIBRE_GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
_DEFAULT_COLOR = "#0F2D53"
_DEFAULT_STROKE = "#0a2140"
_SOURCE_ID = "geolayers"


def build_layer_paint_layers(
    *,
    layer: LayerInfo,
    source_id: str,
    style: dict | None = None,
    label_config: dict | None = None,
    opacity: float | None = None,
    visibility: str = "visible",
) -> tuple[list[dict], bool]:
    """Return ``(style_layers, needs_glyphs)`` matching map_builder.js paint rules.

    ``style`` / ``label_config`` default to the layer's saved values. Callers may
    pass a merged style (e.g. map ``style_override``) or a map-level opacity.
    """
    style = {**(layer.style or {}), **(style or {})}
    label_config = label_config if label_config is not None else (layer.label_config or {})
    table = layer.table_name
    geom = layer.geometry_type or ""
    color = style.get("color") or _DEFAULT_COLOR
    stroke_color = style.get("strokeColor") or _DEFAULT_STROKE
    stroke_width = style.get("strokeWidth")
    # Map-level opacity wins when provided; otherwise layer style opacity.
    layer_opacity = opacity if opacity is not None else style.get("opacity")
    layout = {"visibility": visibility}
    layers: list[dict] = []

    if geom in (LayerInfo.GeometryType.POINT, LayerInfo.GeometryType.MULTIPOINT):
        layers.append(
            {
                "id": f"{table}-circle",
                "type": "circle",
                "source": source_id,
                "source-layer": table,
                "layout": layout,
                "paint": {
                    "circle-color": color,
                    "circle-radius": 5,
                    "circle-stroke-color": stroke_color,
                    "circle-stroke-width": stroke_width if stroke_width is not None else 1,
                    "circle-opacity": layer_opacity if layer_opacity is not None else 0.8,
                },
            }
        )
    elif geom in (LayerInfo.GeometryType.LINESTRING, LayerInfo.GeometryType.MULTILINESTRING):
        layers.append(
            {
                "id": f"{table}-line",
                "type": "line",
                "source": source_id,
                "source-layer": table,
                "layout": layout,
                "paint": {
                    "line-color": color,
                    "line-width": stroke_width if stroke_width is not None else 2,
                    "line-opacity": layer_opacity if layer_opacity is not None else 1,
                },
            }
        )
    else:
        layers.append(
            {
                "id": f"{table}-fill",
                "type": "fill",
                "source": source_id,
                "source-layer": table,
                "layout": layout,
                "paint": {
                    "fill-color": color,
                    "fill-opacity": layer_opacity if layer_opacity is not None else 0.6,
                },
            }
        )
        layers.append(
            {
                "id": f"{table}-outline",
                "type": "line",
                "source": source_id,
                "source-layer": table,
                "layout": layout,
                "paint": {
                    "line-color": stroke_color,
                    "line-width": stroke_width if stroke_width is not None else 1,
                },
            }
        )
        if geom in (LayerInfo.GeometryType.GEOMETRY, ""):
            layers.append(
                {
                    "id": f"{table}-line-fallback",
                    "type": "line",
                    "source": source_id,
                    "source-layer": table,
                    "layout": layout,
                    "paint": {
                        "line-color": color,
                        "line-width": stroke_width if stroke_width is not None else 2,
                        "line-opacity": layer_opacity if layer_opacity is not None else 1,
                    },
                }
            )

    label_field = (label_config.get("field") or "").strip()
    needs_glyphs = bool(label_field)
    if label_field:
        layers.append(
            {
                "id": f"{table}-label",
                "type": "symbol",
                "source": source_id,
                "source-layer": table,
                "layout": {
                    **layout,
                    "text-field": ["get", label_field],
                    "text-size": label_config.get("size") or 12,
                    "text-anchor": "top",
                    "text-font": ["Open Sans Regular"],
                },
                "paint": {
                    "text-color": label_config.get("color") or _DEFAULT_COLOR,
                },
            }
        )

    return layers, needs_glyphs


def build_share_style(*, layer: LayerInfo, tiles_url: str) -> dict:
    """Return a Mapbox Style Spec v8 document for a single shared ``layer``.

    ``tiles_url`` must be an absolute XYZ template ending in ``{z}/{x}/{y}.pbf``
    for this share token. Style is read live from the layer so edits propagate
    without recreating the share link.
    """
    paint_layers, needs_glyphs = build_layer_paint_layers(layer=layer, source_id=_SOURCE_ID)
    style = layer.style or {}
    label_config = layer.label_config or {}
    table = layer.table_name
    geom = layer.geometry_type or ""

    doc: dict = {
        "version": 8,
        "name": layer.name,
        "metadata": {
            "geolayers:source_layer": table,
            "geolayers:geometry_type": geom,
            "geolayers:suggested_geometry": SUGGESTED_GEOMETRY.get(geom, "line"),
            "geolayers:style": style,
            "geolayers:label_config": label_config,
        },
        "sources": {
            _SOURCE_ID: {
                "type": "vector",
                "tiles": [tiles_url],
                "minzoom": 0,
                "maxzoom": 22,
            }
        },
        "layers": paint_layers,
    }
    if needs_glyphs:
        doc["glyphs"] = MAPLIBRE_GLYPHS
    return doc
