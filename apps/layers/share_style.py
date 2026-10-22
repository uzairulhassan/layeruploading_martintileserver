"""Build a Mapbox Style Spec for an externally shared layer.

Tiles stay raw MVT; this document mirrors the paint/layout the GeoLayers map
builder applies from ``LayerInfo.style`` / ``label_config``, so another MapLibre
or Mapbox client can load ``/x/<token>/style.json`` and match in-app styling.
"""
from __future__ import annotations

from .geometry_hints import SUGGESTED_GEOMETRY
from .models import LayerInfo

# Free public glyphs so symbol (label) layers work without a Mapbox token.
_MAPLIBRE_GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
_DEFAULT_COLOR = "#0F2D53"
_DEFAULT_STROKE = "#0a2140"
_SOURCE_ID = "geolayers"


def build_share_style(*, layer: LayerInfo, tiles_url: str) -> dict:
    """Return a Mapbox Style Spec v8 document for ``layer``.

    ``tiles_url`` must be an absolute XYZ template ending in ``{z}/{x}/{y}.pbf``
    for this share token. Style is read live from the layer so edits propagate
    without recreating the share link.
    """
    style = layer.style or {}
    label_config = layer.label_config or {}
    table = layer.table_name
    geom = layer.geometry_type or ""
    color = style.get("color") or _DEFAULT_COLOR
    stroke_color = style.get("strokeColor") or _DEFAULT_STROKE
    stroke_width = style.get("strokeWidth")
    opacity = style.get("opacity")

    layers: list[dict] = []

    if geom in (LayerInfo.GeometryType.POINT, LayerInfo.GeometryType.MULTIPOINT):
        layers.append(
            {
                "id": f"{table}-circle",
                "type": "circle",
                "source": _SOURCE_ID,
                "source-layer": table,
                "paint": {
                    "circle-color": color,
                    "circle-radius": 5,
                    "circle-stroke-color": stroke_color,
                    "circle-stroke-width": stroke_width if stroke_width is not None else 1,
                    "circle-opacity": opacity if opacity is not None else 0.8,
                },
            }
        )
    elif geom in (LayerInfo.GeometryType.LINESTRING, LayerInfo.GeometryType.MULTILINESTRING):
        layers.append(
            {
                "id": f"{table}-line",
                "type": "line",
                "source": _SOURCE_ID,
                "source-layer": table,
                "paint": {
                    "line-color": color,
                    "line-width": stroke_width if stroke_width is not None else 2,
                    "line-opacity": opacity if opacity is not None else 1,
                },
            }
        )
    else:
        # Polygon / MultiPolygon / Geometry fallback — same as map_builder.js
        layers.append(
            {
                "id": f"{table}-fill",
                "type": "fill",
                "source": _SOURCE_ID,
                "source-layer": table,
                "paint": {
                    "fill-color": color,
                    "fill-opacity": opacity if opacity is not None else 0.6,
                },
            }
        )
        layers.append(
            {
                "id": f"{table}-outline",
                "type": "line",
                "source": _SOURCE_ID,
                "source-layer": table,
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
                    "source": _SOURCE_ID,
                    "source-layer": table,
                    "paint": {
                        "line-color": color,
                        "line-width": stroke_width if stroke_width is not None else 2,
                        "line-opacity": opacity if opacity is not None else 1,
                    },
                }
            )

    label_field = (label_config.get("field") or "").strip()
    if label_field:
        layers.append(
            {
                "id": f"{table}-label",
                "type": "symbol",
                "source": _SOURCE_ID,
                "source-layer": table,
                "layout": {
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
        "layers": layers,
    }
    if label_field:
        doc["glyphs"] = _MAPLIBRE_GLYPHS
    return doc
