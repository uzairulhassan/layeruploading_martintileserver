"""Build Mapbox Style Spec paint/layout for GeoLayers layers.

Single source of truth for:
* Layer URL ``/x/<token>/style.json``
* Map URL ``/m/<token>/style.json``
* In-app map builder via ``MapLayerSerializer.style_layers``

Style JSON (backward compatible)::

    {
      "color": "#0F2D53",
      "strokeColor": "#0a2140",
      "strokeWidth": 1,
      "opacity": 0.6,
      "useSourceColors": false,
      "colorBy": {
        "field": "<any attribute from this layer>",
        "default": "#888888",
        "categories": {"value_a": "#2563eb", "value_b": "#16a34a"}
      },
      "marker": {
        "type": "circle" | "icon",
        "size": 1.0,
        "icon": "gl-poi",
        "iconBy": {
          "field": "<any attribute from this layer>",
          "default": "gl-poi",
          "defaultSize": 1.0,
          "categories": {
            "value_a": {"icon": "gl-square", "size": 1.0},
            "value_b": {"icon": "gl-triangle", "size": 1.5}
          }
        }
      }
    }

Editor writes ``categories`` as ``{icon, size}``. Readers still accept legacy string
values (``"gl-square"`` → icon + ``marker.size`` / ``defaultSize``).

``marker.size`` scales density zoom curves for circles and for icons when Icon by is
off (same icon for all). With ``iconBy``, each category uses its own ``size``.
Lines/polygons use ``strokeWidth``.

Categorical colors become MapLibre ``match`` expressions. Point icons use
``symbol`` layers with SDF ``icon-image`` ids registered by GeoLayers clients
(``map_builder`` and ``geotrak-maps-component``).

Professional defaults (any layer, not dataset-specific):
* Point icons/circles and line widths scale with zoom (thin/small at city overview)
* Icons and labels declutter (collision) instead of stacking into opaque blobs
* Labels appear only once the map is zoomed in enough to read them
"""
from __future__ import annotations

import math

from .models import LayerInfo

# Free public glyphs so symbol (label) layers work without a Mapbox token.
MAPLIBRE_GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf"
_DEFAULT_COLOR = "#0F2D53"
_DEFAULT_STROKE = "#0a2140"
_SOURCE_ID = "geolayers"

# Labels are available from city overview; collision + small size keep them tidy.
_LABEL_MINZOOM = 9

# Per-tier zoom curves: always visible from city overview; dense stays soft/small,
# then grows when zoomed in. Never hide a checked layer behind minzoom.
_ICON_SIZE_CURVES = {
    "sparse": (8, 0.5, 10, 0.62, 12, 0.78, 14, 0.96, 16, 1.12),
    "medium": (8, 0.36, 10, 0.46, 12, 0.62, 14, 0.84, 16, 1.04),
    "dense": (8, 0.24, 10, 0.32, 12, 0.48, 14, 0.74, 16, 0.98),
    "very_dense": (8, 0.2, 10, 0.26, 12, 0.42, 14, 0.68, 16, 0.94),
}
_CIRCLE_RADIUS_CURVES = {
    "sparse": (8, 3.75, 11, 5.0, 14, 6.5, 16, 7.75),
    "medium": (8, 3.0, 11, 4.2, 14, 5.75, 16, 7.0),
    "dense": (8, 2.2, 11, 3.4, 14, 5.25, 16, 6.75),
    "very_dense": (8, 1.9, 11, 2.9, 14, 4.9, 16, 6.5),
}
_ICON_HALO_CURVES = {
    "sparse": (8, 1.1, 12, 1.4, 16, 1.8),
    "medium": (8, 0.9, 12, 1.2, 16, 1.6),
    "dense": (8, 0.25, 12, 0.75, 16, 1.35),
    "very_dense": (8, 0.15, 12, 0.65, 16, 1.25),
}


def _zoom_interpolate(*stops: float) -> list:
    """Build MapLibre linear zoom interpolate from flat zoom/value pairs."""
    expr: list = ["interpolate", ["linear"], ["zoom"]]
    expr.extend(stops)
    return expr


def _density_profile(feature_count: object) -> dict:
    """Generic density tiers from layer feature_count (not dataset-specific names)."""
    try:
        count = max(0, int(feature_count or 0))
    except (TypeError, ValueError):
        count = 0
    # sparse: few features; medium: modest networks; dense/very_dense: city-wide layers
    if count <= 100:
        tier = "sparse"
        return {
            "tier": tier,
            "icon_size": _zoom_interpolate(*_ICON_SIZE_CURVES[tier]),
            "circle_radius": _zoom_interpolate(*_CIRCLE_RADIUS_CURVES[tier]),
            "icon_halo": _zoom_interpolate(*_ICON_HALO_CURVES[tier]),
            "line_scale": 1.2,
            "point_opacity_far": 1.0,
            "point_opacity_near": 1.0,
            "line_opacity": 0.95,
            "icon_padding": 2,
            "label_minzoom": _LABEL_MINZOOM,
        }
    if count <= 400:
        tier = "medium"
        return {
            "tier": tier,
            "icon_size": _zoom_interpolate(*_ICON_SIZE_CURVES[tier]),
            "circle_radius": _zoom_interpolate(*_CIRCLE_RADIUS_CURVES[tier]),
            "icon_halo": _zoom_interpolate(*_ICON_HALO_CURVES[tier]),
            "line_scale": 0.85,
            "point_opacity_far": 0.88,
            "point_opacity_near": 0.95,
            "line_opacity": 0.88,
            "icon_padding": 1,
            "label_minzoom": _LABEL_MINZOOM + 1,
        }
    if count <= 2000:
        tier = "dense"
        return {
            "tier": tier,
            "icon_size": _zoom_interpolate(*_ICON_SIZE_CURVES[tier]),
            "circle_radius": _zoom_interpolate(*_CIRCLE_RADIUS_CURVES[tier]),
            "icon_halo": _zoom_interpolate(*_ICON_HALO_CURVES[tier]),
            "line_scale": 0.65,
            "point_opacity_far": 0.48,
            "point_opacity_near": 0.9,
            "line_opacity": 0.8,
            "icon_padding": 1,
            "label_minzoom": _LABEL_MINZOOM + 2,
        }
    tier = "very_dense"
    return {
        "tier": tier,
        "icon_size": _zoom_interpolate(*_ICON_SIZE_CURVES[tier]),
        "circle_radius": _zoom_interpolate(*_CIRCLE_RADIUS_CURVES[tier]),
        "icon_halo": _zoom_interpolate(*_ICON_HALO_CURVES[tier]),
        "line_scale": 0.55,
        "point_opacity_far": 0.4,
        "point_opacity_near": 0.88,
        "line_opacity": 0.75,
        "icon_padding": 0,
        "label_minzoom": _LABEL_MINZOOM + 3,
    }


def _point_opacity_paint(layer_opacity: object, density: dict):
    """Softer at city overview for dense tiers; full (capped) strength when zoomed in."""
    near = density["point_opacity_near"]
    far = density["point_opacity_far"]
    if layer_opacity is not None:
        try:
            cap = max(0.0, min(1.0, float(layer_opacity)))
        except (TypeError, ValueError):
            cap = near
        near = min(near, cap)
        far = min(far, cap)
    if density["tier"] in ("sparse", "medium") or abs(near - far) < 0.02:
        return round(near, 3)
    mid = round((far + near) / 2, 3)
    return _zoom_interpolate(8, round(far, 3), 11, mid, 14, round(near, 3))

# Built-in SDF icon ids registered by GeoLayers viewers.
GEOLAYERS_ICON_IDS = (
    "gl-poi",
    "gl-station",
    "gl-underground",
    "gl-elevated",
    "gl-bus",
    "gl-metro",
    "gl-square",
    "gl-triangle",
    "gl-diamond",
)
_DEFAULT_ICON = "gl-poi"


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_hex(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text
        except ValueError:
            return fallback
    return fallback


def _safe_icon_id(value: object, fallback: str = _DEFAULT_ICON) -> str:
    if isinstance(value, dict):
        value = value.get("icon")
    text = str(value or "").strip()
    return text if text in GEOLAYERS_ICON_IDS else fallback


def _clamp_marker_size(value: object, fallback: float = 1.0) -> float:
    try:
        scale = float(fallback if value is None else value)
    except (TypeError, ValueError):
        scale = float(fallback)
    return max(0.25, min(4.0, scale))


def _icon_category_spec(
    raw: object, *, default_icon: str = _DEFAULT_ICON, default_size: float = 1.0
) -> tuple[str, float]:
    """Normalize iconBy category values: legacy string or ``{icon, size}``."""
    if isinstance(raw, dict):
        return (
            _safe_icon_id(raw.get("icon"), default_icon),
            _clamp_marker_size(raw.get("size"), default_size),
        )
    return _safe_icon_id(raw, default_icon), _clamp_marker_size(default_size, 1.0)


def _match_expression(field: str, categories: dict, default, *, coerce_icon: bool = False):
    """Build ``["match", ["to-string", ["get", field]], key, val, …, default]``.

    ``to-string`` keeps numeric MVT attributes comparable to string category keys.
    """
    field = (field or "").strip()
    if not field:
        return default
    expr: list = ["match", ["to-string", ["get", field]]]
    for raw_key, raw_val in (categories or {}).items():
        key = str(raw_key)
        if key == "":
            continue
        if coerce_icon:
            val = _safe_icon_id(raw_val)
        else:
            val = _normalize_hex(raw_val, str(default))
        expr.extend([key, val])
    if len(expr) == 2:
        return default
    expr.append(default)
    return expr


def _color_expression(style: dict, *, fallback: str, kml_column: str | None = None):
    """Resolve paint color: colorBy → KML source colour → fixed fallback."""
    color_by = _as_dict(style.get("colorBy"))
    field = (color_by.get("field") or "").strip()
    if field:
        default = _normalize_hex(color_by.get("default"), fallback)
        categories = _as_dict(color_by.get("categories"))
        return _match_expression(field, categories, default)
    if kml_column and style.get("useSourceColors"):
        return ["to-color", ["get", kml_column], fallback]
    return fallback


def _feature_width(style: dict, fallback: float):
    if style.get("useSourceColors"):
        return ["case", ["has", "kml_width"], ["to-number", ["get", "kml_width"]], fallback]
    return fallback


def _zoom_scaled_line_width(base_width: object, *, density_scale: float = 1.0):
    """Keep corridors tidy at city zoom; grow toward the authored width when close."""
    density_scale = max(0.35, float(density_scale or 1.0))
    zoom_factor = [
        "interpolate",
        ["linear"],
        ["zoom"],
        8,
        0.45,
        11,
        0.7,
        14,
        0.9,
        16,
        1.0,
    ]
    if isinstance(base_width, (int, float)):
        width = float(base_width) * density_scale
        return [
            "interpolate",
            ["linear"],
            ["zoom"],
            8,
            round(max(0.55, width * 0.45), 2),
            11,
            round(max(0.85, width * 0.7), 2),
            14,
            round(max(1.1, width * 0.9), 2),
            16,
            round(width, 2),
        ]
    return ["*", ["*", base_width, density_scale], zoom_factor]


def _label_text_size(label_config: dict):
    size = label_config.get("size") or 12
    try:
        size = float(size)
    except (TypeError, ValueError):
        size = 12.0
    return [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        max(9.0, round(size * 0.72, 1)),
        12,
        max(10.0, round(size * 0.9, 1)),
        15,
        size,
        17,
        size + 1,
    ]


def _point_label_layout(*, label_field: str, label_config: dict, has_icons: bool) -> dict:
    """Point labels: try alternate anchors so names avoid icons and each other."""
    radial = 1.35 if has_icons else 0.95
    return {
        "text-field": ["get", label_field],
        "text-size": _label_text_size(label_config),
        "text-font": ["Open Sans Regular"],
        "text-variable-anchor": [
            "top",
            "bottom",
            "left",
            "right",
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
        ],
        "text-radial-offset": radial,
        "text-justify": "auto",
        "text-max-width": 9,
        "text-optional": True,
        "text-allow-overlap": False,
        "text-ignore-placement": False,
        "text-padding": 6,
        "symbol-z-order": "viewport-y",
    }


def _line_label_layout(*, label_field: str, label_config: dict) -> dict:
    """Line labels follow the path and space out so they do not stack."""
    return {
        "symbol-placement": "line",
        "symbol-spacing": 280,
        "text-field": ["get", label_field],
        "text-size": _label_text_size(label_config),
        "text-font": ["Open Sans Regular"],
        "text-rotation-alignment": "map",
        "text-pitch-alignment": "viewport",
        "text-max-angle": 25,
        "text-keep-upright": True,
        "text-max-width": 12,
        "text-optional": True,
        "text-allow-overlap": False,
        "text-ignore-placement": False,
        "text-padding": 10,
    }


def _fill_label_layout(*, label_field: str, label_config: dict) -> dict:
    """Polygon labels sit in free space around the feature center."""
    return {
        "text-field": ["get", label_field],
        "text-size": _label_text_size(label_config),
        "text-font": ["Open Sans Regular"],
        "text-variable-anchor": ["center", "top", "bottom", "left", "right"],
        "text-radial-offset": 0.4,
        "text-justify": "auto",
        "text-max-width": 10,
        "text-optional": True,
        "text-allow-overlap": False,
        "text-ignore-placement": False,
        "text-padding": 8,
    }


def _marker_config(style: dict) -> dict:
    return _as_dict(style.get("marker"))


def _marker_size_scale(style: dict) -> float:
    """User size multiplier for circles / same-for-all icons (1 = density default)."""
    return _clamp_marker_size(_marker_config(style).get("size"), 1.0)


def _scale_paint_expr(expr: object, scale: float):
    """Scale a zoom curve or number without nesting ``zoom`` under ``*``.

    Mapbox requires ``["zoom"]`` only as the input of a top-level ``interpolate`` /
    ``step``. So we multiply stop values in place instead of wrapping the curve.
    """
    if abs(scale - 1.0) < 0.001:
        return expr
    scale = round(float(scale), 3)
    if isinstance(expr, (int, float)):
        return round(float(expr) * scale, 4)
    if not isinstance(expr, list) or not expr:
        return expr
    op = expr[0]
    if op == "interpolate" and len(expr) >= 5:
        # ["interpolate", type, input, z1, v1, z2, v2, ...]
        out = list(expr)
        for i in range(4, len(out), 2):
            if isinstance(out[i], (int, float)):
                out[i] = round(float(out[i]) * scale, 4)
        return out
    if op == "step" and len(expr) >= 3:
        # ["step", input, v0, z1, v1, ...]
        out = list(expr)
        if isinstance(out[2], (int, float)):
            out[2] = round(float(out[2]) * scale, 4)
        for i in range(4, len(out), 2):
            if isinstance(out[i], (int, float)):
                out[i] = round(float(out[i]) * scale, 4)
        return out
    return expr


def _icon_size_expression(style: dict, base_curve: object):
    """Point icon-size: global ``marker.size``, or per ``iconBy`` category size.

    Per-value sizes stay Mapbox-valid by putting ``match`` *inside* each zoom stop
    of the density interpolate (``zoom`` remains the top-level input).
    """
    marker = _marker_config(style)
    icon_by = _as_dict(marker.get("iconBy"))
    field = (icon_by.get("field") or "").strip()
    global_size = _marker_size_scale(style)
    if not field:
        return _scale_paint_expr(base_curve, global_size)

    default_icon = _safe_icon_id(icon_by.get("default"), _safe_icon_id(marker.get("icon")))
    default_size = _clamp_marker_size(icon_by.get("defaultSize"), global_size)
    size_by_key: dict[str, float] = {}
    for raw_key, raw_val in _as_dict(icon_by.get("categories")).items():
        key = str(raw_key)
        if key == "":
            continue
        _icon, size = _icon_category_spec(
            raw_val, default_icon=default_icon, default_size=default_size
        )
        size_by_key[key] = size

    if not size_by_key or all(abs(size - default_size) < 0.001 for size in size_by_key.values()):
        return _scale_paint_expr(base_curve, default_size)

    if not isinstance(base_curve, list) or not base_curve or base_curve[0] != "interpolate":
        return _scale_paint_expr(base_curve, default_size)

    out = list(base_curve)
    for i in range(4, len(out), 2):
        base_val = out[i]
        if not isinstance(base_val, (int, float)):
            continue
        match_expr: list = ["match", ["to-string", ["get", field]]]
        for key, size in size_by_key.items():
            match_expr.extend([key, round(float(base_val) * size, 4)])
        match_expr.append(round(float(base_val) * default_size, 4))
        out[i] = match_expr
    return out


def _uses_point_icons(style: dict) -> bool:
    """Icons only when the user explicitly chose marker type ``icon``."""
    return str(_marker_config(style).get("type") or "circle").lower() == "icon"


def _color_by_active(style: dict) -> bool:
    return bool((_as_dict(style.get("colorBy")).get("field") or "").strip())


def _icon_image_expression(style: dict):
    marker = _marker_config(style)
    icon_by = _as_dict(marker.get("iconBy"))
    default_icon = _safe_icon_id(marker.get("icon"), _DEFAULT_ICON)
    field = (icon_by.get("field") or "").strip()
    if not field:
        return default_icon
    categories = _as_dict(icon_by.get("categories"))
    default = _safe_icon_id(icon_by.get("default"), default_icon)
    return _match_expression(field, categories, default, coerce_icon=True)


def _collect_required_icons(style: dict) -> list[str]:
    if not _uses_point_icons(style):
        return []
    marker = _marker_config(style)
    icons = {_safe_icon_id(marker.get("icon"), _DEFAULT_ICON)}
    icon_by = _as_dict(marker.get("iconBy"))
    if icon_by:
        icons.add(_safe_icon_id(icon_by.get("default"), _DEFAULT_ICON))
        for value in _as_dict(icon_by.get("categories")).values():
            icons.add(_safe_icon_id(value))
    return sorted(icons)


_ICON_LABELS = {
    "gl-poi": "Pin",
    "gl-station": "Station",
    "gl-underground": "Underground",
    "gl-elevated": "Elevated",
    "gl-bus": "Bus",
    "gl-metro": "Metro",
    "gl-square": "Square",
    "gl-triangle": "Triangle",
    "gl-diamond": "Diamond",
}


def build_style_legend(style: dict | None, *, title: str = "") -> dict | None:
    """Build an end-user legend from categorical ``colorBy`` / ``iconBy`` style.

    Returns ``None`` when the layer has no attribute categories (single paint only).
    Generic for any uploaded layer — field names and values come from the style JSON.
    """
    style = style if isinstance(style, dict) else {}
    color_by = _as_dict(style.get("colorBy"))
    marker = _marker_config(style)
    icon_by = _as_dict(marker.get("iconBy")) if _uses_point_icons(style) else {}

    color_field = (color_by.get("field") or "").strip()
    icon_field = (icon_by.get("field") or "").strip()
    if not color_field and not icon_field:
        return None

    color_cats = _as_dict(color_by.get("categories")) if color_field else {}
    icon_cats = _as_dict(icon_by.get("categories")) if icon_field else {}
    default_color = _normalize_hex(
        color_by.get("default") if color_field else style.get("color"),
        _normalize_hex(style.get("color"), _DEFAULT_COLOR),
    )
    default_icon = _safe_icon_id(
        icon_by.get("default") if icon_field else marker.get("icon"),
        _safe_icon_id(marker.get("icon"), _DEFAULT_ICON),
    )

    # Prefer one section field when both target the same attribute.
    if color_field and icon_field and color_field == icon_field:
        keys = list(dict.fromkeys([*color_cats.keys(), *icon_cats.keys()]))
        items = []
        for key in keys:
            icon_id = _safe_icon_id(icon_cats.get(key), default_icon)
            items.append(
                {
                    "label": str(key),
                    "color": _normalize_hex(color_cats.get(key), default_color),
                    "icon": icon_id,
                    "iconLabel": _ICON_LABELS.get(icon_id, ""),
                }
            )
        if not items:
            return None
        return {
            "title": (title or "").strip(),
            "field": color_field,
            "items": items,
        }

    sections: list[dict] = []
    if color_field and color_cats:
        sections.append(
            {
                "title": (title or "").strip(),
                "field": color_field,
                "items": [
                    {
                        "label": str(key),
                        "color": _normalize_hex(color_cats.get(key), default_color),
                        "icon": None,
                        "iconLabel": "",
                    }
                    for key in color_cats.keys()
                ],
            }
        )
    if icon_field and icon_cats:
        icon_items = []
        for key in icon_cats.keys():
            icon_id = _safe_icon_id(icon_cats.get(key), default_icon)
            icon_items.append(
                {
                    "label": str(key),
                    "color": default_color,
                    "icon": icon_id,
                    "iconLabel": _ICON_LABELS.get(icon_id, ""),
                }
            )
        sections.append(
            {
                "title": (title or "").strip(),
                "field": icon_field,
                "items": icon_items,
            }
        )
    if not sections:
        return None
    if len(sections) == 1:
        section = sections[0]
        return {
            "title": section["title"],
            "field": section["field"],
            "items": section["items"],
        }
    return {
        "title": (title or "").strip(),
        "field": "",
        "sections": sections,
    }


def build_layer_paint_layers(
    *,
    layer: LayerInfo,
    source_id: str,
    style: dict | None = None,
    label_config: dict | None = None,
    opacity: float | None = None,
    visibility: str = "visible",
    id_prefix: str | None = None,
    replace_style: bool = False,
    replace_label_config: bool = False,
) -> tuple[list[dict], bool, list[str]]:
    """Return ``(style_layers, needs_glyphs, required_icons)``.

    ``style`` / ``label_config`` default to the layer's saved values. Callers may
    pass a merged style (e.g. map ``style_override``) or a map-level opacity.
    ``id_prefix`` defaults to the PostGIS table name (share links); the in-app map
    builder passes ``layer-<map_layer_id>``.

    Style modal live preview passes ``replace_style`` / ``replace_label_config`` so
    the draft form fully replaces saved paint (merge would keep stale colorBy etc.).
    """
    if replace_style:
        style = dict(style or {})
    else:
        style = {**(layer.style or {}), **(style or {})}
    if replace_label_config:
        label_config = dict(label_config or {})
    else:
        label_config = label_config if label_config is not None else (layer.label_config or {})
    table = layer.table_name
    prefix = id_prefix or table
    geom = layer.geometry_type or ""
    density = _density_profile(getattr(layer, "feature_count", 0))
    color = _normalize_hex(style.get("color"), _DEFAULT_COLOR)
    stroke_color = _normalize_hex(style.get("strokeColor"), _DEFAULT_STROKE)
    stroke_width = style.get("strokeWidth")
    # Map-level opacity wins when provided. KML source colours already include alpha,
    # so skip layer opacity on top of them unless the map sets opacity explicitly.
    if opacity is not None:
        layer_opacity = opacity
    elif style.get("useSourceColors") and not _color_by_active(style):
        layer_opacity = 1
    elif style.get("opacity") is not None:
        layer_opacity = style.get("opacity")
    else:
        layer_opacity = None

    fill_color = _color_expression(style, fallback=color, kml_column="kml_color")
    outline_color = _color_expression(style, fallback=stroke_color, kml_column="kml_stroke")
    layout = {"visibility": visibility}
    layers: list[dict] = []
    required_icons: list[str] = []
    point_size = _marker_size_scale(style)
    icon_size = _icon_size_expression(style, density["icon_size"])
    circle_radius = _scale_paint_expr(density["circle_radius"], point_size)
    icon_halo = density["icon_halo"]
    line_density = density["line_scale"]

    if geom in (LayerInfo.GeometryType.POINT, LayerInfo.GeometryType.MULTIPOINT):
        point_opacity = _point_opacity_paint(layer_opacity, density)
        if _uses_point_icons(style):
            required_icons = _collect_required_icons(style)
            # Always paint from overview; density only softens size/opacity (never hides).
            layers.append(
                {
                    "id": f"{prefix}-symbol",
                    "type": "symbol",
                    "source": source_id,
                    "source-layer": table,
                    "layout": {
                        **layout,
                        "icon-image": _icon_image_expression(style),
                        "icon-size": icon_size,
                        "icon-allow-overlap": True,
                        "icon-ignore-placement": True,
                        "icon-padding": density["icon_padding"],
                    },
                    "paint": {
                        "icon-color": fill_color,
                        "icon-opacity": point_opacity,
                        "icon-halo-color": "#ffffff",
                        "icon-halo-width": icon_halo,
                        "icon-halo-blur": 0.35,
                    },
                }
            )
        else:
            layers.append(
                {
                    "id": f"{prefix}-circle",
                    "type": "circle",
                    "source": source_id,
                    "source-layer": table,
                    "layout": layout,
                    "paint": {
                        "circle-color": fill_color,
                        "circle-radius": circle_radius,
                        # White ring keeps categorical colours readable on any basemap.
                        "circle-stroke-color": "#ffffff",
                        "circle-stroke-width": stroke_width if stroke_width is not None else 1.25,
                        "circle-opacity": point_opacity,
                        "circle-stroke-opacity": 1,
                    },
                }
            )
    elif geom in (LayerInfo.GeometryType.LINESTRING, LayerInfo.GeometryType.MULTILINESTRING):
        line_opacity = (
            layer_opacity if layer_opacity is not None else density["line_opacity"]
        )
        base_width = _feature_width(style, stroke_width if stroke_width is not None else 2)
        layers.append(
            {
                "id": f"{prefix}-line",
                "type": "line",
                "source": source_id,
                "source-layer": table,
                "layout": {
                    **layout,
                    "line-cap": "round",
                    "line-join": "round",
                },
                "paint": {
                    "line-color": fill_color,
                    "line-width": _zoom_scaled_line_width(
                        base_width, density_scale=line_density
                    ),
                    "line-opacity": line_opacity,
                },
            }
        )
    else:
        layers.append(
            {
                "id": f"{prefix}-fill",
                "type": "fill",
                "source": source_id,
                "source-layer": table,
                "layout": layout,
                "paint": {
                    "fill-color": fill_color,
                    "fill-opacity": layer_opacity if layer_opacity is not None else 0.45,
                },
            }
        )
        outline_base = _feature_width(style, stroke_width if stroke_width is not None else 1)
        layers.append(
            {
                "id": f"{prefix}-outline",
                "type": "line",
                "source": source_id,
                "source-layer": table,
                "layout": {
                    **layout,
                    "line-cap": "round",
                    "line-join": "round",
                },
                "paint": {
                    "line-color": outline_color,
                    "line-width": _zoom_scaled_line_width(
                        outline_base, density_scale=line_density
                    ),
                    "line-opacity": 0.85,
                },
            }
        )
        if geom in (LayerInfo.GeometryType.GEOMETRY, ""):
            fallback_width = stroke_width if stroke_width is not None else 2
            layers.append(
                {
                    "id": f"{prefix}-line-fallback",
                    "type": "line",
                    "source": source_id,
                    "source-layer": table,
                    "layout": {
                        **layout,
                        "line-cap": "round",
                        "line-join": "round",
                    },
                    "paint": {
                        "line-color": fill_color,
                        "line-width": _zoom_scaled_line_width(
                            fallback_width, density_scale=line_density
                        ),
                        "line-opacity": layer_opacity
                        if layer_opacity is not None
                        else density["line_opacity"],
                    },
                }
            )

    label_field = (label_config.get("field") or "").strip()
    needs_glyphs = bool(label_field)
    if label_field:
        is_point = geom in (LayerInfo.GeometryType.POINT, LayerInfo.GeometryType.MULTIPOINT)
        is_line = geom in (
            LayerInfo.GeometryType.LINESTRING,
            LayerInfo.GeometryType.MULTILINESTRING,
        )
        if is_point:
            label_layout = _point_label_layout(
                label_field=label_field,
                label_config=label_config,
                has_icons=bool(required_icons),
            )
        elif is_line:
            label_layout = _line_label_layout(
                label_field=label_field,
                label_config=label_config,
            )
        else:
            label_layout = _fill_label_layout(
                label_field=label_field,
                label_config=label_config,
            )
        layers.append(
            {
                "id": f"{prefix}-label",
                "type": "symbol",
                "source": source_id,
                "source-layer": table,
                "minzoom": density["label_minzoom"],
                "layout": {
                    **layout,
                    **label_layout,
                },
                "paint": {
                    "text-color": label_config.get("color") or _DEFAULT_COLOR,
                    "text-halo-color": "#ffffff",
                    "text-halo-width": [
                        "interpolate",
                        ["linear"],
                        ["zoom"],
                        9,
                        1.1,
                        14,
                        1.5,
                        17,
                        1.75,
                    ],
                    "text-halo-blur": 0.25,
                    "text-opacity": [
                        "interpolate",
                        ["linear"],
                        ["zoom"],
                        9,
                        0.88,
                        12,
                        0.95,
                        15,
                        1,
                    ],
                },
            }
        )

    return layers, needs_glyphs, required_icons


def viewport_from_bounds(bounds: object) -> dict | None:
    """Derive MapLibre ``center`` / ``zoom`` plus normalized bounds from layer extents."""
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(v) for v in bounds)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        return None
    if maxx <= minx or maxy <= miny:
        return None
    center_lng = (minx + maxx) / 2.0
    center_lat = (miny + maxy) / 2.0
    lng_span = max(maxx - minx, 1e-6)
    lat_span = max(maxy - miny, 1e-6)
    # Rough web-mercator zoom from the larger geographic span.
    zoom = math.floor(math.log2(360.0 / max(lng_span, lat_span * 1.25)))
    zoom = float(max(1, min(14, zoom)))
    return {
        "center": [round(center_lng, 6), round(center_lat, 6)],
        "zoom": zoom,
        "bounds": [minx, miny, maxx, maxy],
    }


def build_share_style(*, layer: LayerInfo, tiles_url: str) -> dict:
    """Return a Mapbox Style Spec v8 document for a single shared ``layer``.

    ``tiles_url`` must be an absolute XYZ template ending in ``{z}/{x}/{y}.pbf``
    for this share token. Style is read live from the layer so edits propagate
    without recreating the share link. When ``layer.bounds`` is known, ``center``,
    ``zoom``, and ``metadata.geolayers:bounds`` are set so viewers can fit the layer.
    """
    paint_layers, needs_glyphs, required_icons = build_layer_paint_layers(
        layer=layer, source_id=_SOURCE_ID
    )
    style = layer.style or {}
    label_config = layer.label_config or {}
    table = layer.table_name
    geom = layer.geometry_type or ""

    legend = build_style_legend(style, title=layer.name)
    metadata = {
        "geolayers:source_layer": table,
        "geolayers:geometry_type": geom,
        "geolayers:style": style,
        "geolayers:label_config": label_config,
        "geolayers:attribute_schema": layer.attribute_schema or [],
        "geolayers:required_icons": required_icons,
        "geolayers:legend": [legend] if legend else [],
        "geolayers:kind": "layer",
    }
    doc: dict = {
        "version": 8,
        "name": layer.name,
        "metadata": metadata,
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
    viewport = viewport_from_bounds(layer.bounds)
    if viewport:
        doc["center"] = viewport["center"]
        doc["zoom"] = viewport["zoom"]
        metadata["geolayers:bounds"] = viewport["bounds"]
    if needs_glyphs:
        doc["glyphs"] = MAPLIBRE_GLYPHS
    return doc
