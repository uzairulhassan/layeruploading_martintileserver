"""Recommended map layer stacking: zones under routes under POIs.

Lower ``order`` draws first (underneath). Higher ``order`` draws on top and
wins feature click hit-testing — so points should sit above lines/polygons.
"""
from __future__ import annotations

from apps.layers.models import LayerInfo

from .models import MapLayer, MapProject


def geometry_stack_rank(geometry_type: str | None) -> int:
    """0 = bottom (zones), 1 = routes/roads, 2 = POIs (top)."""
    geom = (geometry_type or "").strip()
    if geom in (
        LayerInfo.GeometryType.POLYGON,
        LayerInfo.GeometryType.MULTIPOLYGON,
    ):
        return 0
    if geom in (
        LayerInfo.GeometryType.LINESTRING,
        LayerInfo.GeometryType.MULTILINESTRING,
    ):
        return 1
    if geom in (
        LayerInfo.GeometryType.POINT,
        LayerInfo.GeometryType.MULTIPOINT,
    ):
        return 2
    # Mixed / unknown Geometry → treat like routes (middle).
    return 1


def apply_recommended_stack_order(map_project: MapProject) -> list[MapLayer]:
    """Re-number ``MapLayer.order`` by geometry stack rank (stable within rank)."""
    map_layers = list(map_project.map_layers.select_related("layer").order_by("order", "id"))
    map_layers.sort(
        key=lambda ml: (
            geometry_stack_rank(ml.layer.geometry_type),
            ml.order,
            ml.id,
        )
    )
    changed: list[MapLayer] = []
    for idx, map_layer in enumerate(map_layers):
        if map_layer.order != idx:
            map_layer.order = idx
            changed.append(map_layer)
    if changed:
        MapLayer.objects.bulk_update(changed, ["order"])
    return map_layers


def insert_map_layer_with_stack(
    *,
    map_project: MapProject,
    layer: LayerInfo,
    visible: bool = True,
    opacity: float = 1.0,
    style_override=None,
    explicit_order: int | None = None,
) -> MapLayer:
    """Create/update a map layer; without explicit order, insert by geometry band."""
    defaults = {
        "visible": visible,
        "opacity": opacity,
        "style_override": style_override,
    }

    if explicit_order is not None:
        defaults["order"] = explicit_order
        map_layer, _ = MapLayer.objects.update_or_create(
            map=map_project,
            layer=layer,
            defaults=defaults,
        )
        return map_layer

    others = list(
        map_project.map_layers.exclude(layer=layer)
        .select_related("layer")
        .order_by("order", "id")
    )
    rank = geometry_stack_rank(layer.geometry_type)
    insert_at = len(others)
    for idx, map_layer in enumerate(others):
        if geometry_stack_rank(map_layer.layer.geometry_type) > rank:
            insert_at = idx
            break

    defaults["order"] = insert_at
    map_layer, _ = MapLayer.objects.update_or_create(
        map=map_project,
        layer=layer,
        defaults=defaults,
    )

    sequence = others[:insert_at] + [map_layer] + others[insert_at:]
    changed: list[MapLayer] = []
    for idx, item in enumerate(sequence):
        if item.order != idx:
            item.order = idx
            changed.append(item)
    if changed:
        MapLayer.objects.bulk_update(changed, ["order"])
    return map_layer
