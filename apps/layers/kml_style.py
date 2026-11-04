"""Turn OGR feature style strings (resolved from KML ``<Style>``) into GeoLayers colours.

GDAL's LIBKML driver resolves each Placemark's style (inline, ``styleUrl`` or the
``normal`` side of a ``StyleMap``) into an OGR style string, for example
``PEN(c:#FF0000FF,w:3.000000px);BRUSH(fc:#0000FF7F)`` or ``SYMBOL(c:#00FF00FF)``.
Colours are ``#RRGGBB`` or ``#RRGGBBAA`` (GDAL already converted KML's
``aabbggrr`` order).

Each geometry family reads different tools:

* points   - ``SYMBOL`` colour (KML IconStyle)
* lines    - ``PEN`` colour and width (KML LineStyle)
* polygons - ``BRUSH`` fill (KML PolyStyle) plus ``PEN`` outline (KML LineStyle)

No Django imports, so this stays cheap to unit test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

POINT = "point"
LINE = "line"
POLYGON = "polygon"

_TOOL_RE = re.compile(r"(?:^|;)\s*(PEN|BRUSH|SYMBOL)\(([^)]*)\)", re.IGNORECASE)
_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?$")
_NUMBER_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)")
MIN_WIDTH = 0.5
MAX_WIDTH = 20.0


@dataclass(frozen=True)
class Color:
    hex: str  # "#rrggbb"
    alpha: float  # 0..1

    def css(self) -> str:
        """``rgba()`` keeps the KML alpha and parses in both Mapbox GL and MapLibre."""
        r, g, b = (int(self.hex[i:i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r},{g},{b},{round(self.alpha, 3)})"


def _param(params: str, key: str) -> str | None:
    match = re.search(rf"(?:^|,)\s*{key}:([^,]*)", params)
    return match.group(1).strip() if match else None


def _parse_color(value: str | None) -> Color | None:
    match = _COLOR_RE.match((value or "").strip())
    if not match:
        return None
    alpha_hex = match.group(2)
    alpha = int(alpha_hex, 16) / 255 if alpha_hex else 1.0
    return Color(hex=f"#{match.group(1).lower()}", alpha=alpha)


def _parse_width(value: str | None) -> float | None:
    match = _NUMBER_RE.match(value or "")
    if not match:
        return None
    return round(min(max(float(match.group(1)), MIN_WIDTH), MAX_WIDTH), 2)


def parse_ogr_style(style: str | None) -> dict:
    """Return ``{pen_color, pen_width, brush_color, symbol_color}`` (missing keys omitted)."""
    parsed: dict = {}
    if not style or style.lstrip().startswith("@"):  # "@id" = unresolved style reference
        return parsed
    for tool, params in _TOOL_RE.findall(style):
        tool = tool.upper()
        if tool == "PEN":
            if color := _parse_color(_param(params, "c")):
                parsed["pen_color"] = color
            if (width := _parse_width(_param(params, "w"))) is not None:
                parsed["pen_width"] = width
        elif tool == "BRUSH":
            if color := _parse_color(_param(params, "fc")):
                parsed["brush_color"] = color
        elif tool == "SYMBOL":
            if color := _parse_color(_param(params, "c")):
                parsed["symbol_color"] = color
    return parsed


def _family_parts(parsed: dict, family: str) -> tuple[Color | None, Color | None, float | None]:
    """``(main colour, outline colour, width)`` that ``family`` actually draws."""
    if family == POINT:
        return parsed.get("symbol_color"), None, None
    if family == LINE:
        return parsed.get("pen_color"), None, parsed.get("pen_width")
    return parsed.get("brush_color"), parsed.get("pen_color"), parsed.get("pen_width")


def feature_columns(style: str | None, family: str) -> dict:
    """Per-feature values for the ``kml_color`` / ``kml_stroke`` / ``kml_width`` columns."""
    color, stroke, width = _family_parts(parse_ogr_style(style), family)
    return {
        "kml_color": color.css() if color else None,
        "kml_stroke": stroke.css() if stroke else None,
        "kml_width": width,
    }


def layer_style(style: str | None, family: str, *, use_source_colors: bool) -> dict:
    """Seed ``LayerInfo.style`` from the layer's most common KML style.

    The keys are the ones the style editor and map builder already use, so the
    user can change them like any other layer. ``useSourceColors`` tells the map
    to draw each feature in its own KML colour, falling back to ``color``.
    """
    color, stroke, width = _family_parts(parse_ogr_style(style), family)
    result: dict = {}
    if color:
        result["color"] = color.hex
        result["opacity"] = round(color.alpha, 2)
    if stroke:
        result["strokeColor"] = stroke.hex
    if width is not None:
        result["strokeWidth"] = width
    if use_source_colors:
        result["useSourceColors"] = True
    return result
