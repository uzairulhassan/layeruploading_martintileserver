"""Map PostGIS / LayerInfo geometry types → MapLibre paint layer kinds."""
from .models import LayerInfo

SUGGESTED_GEOMETRY = {
    LayerInfo.GeometryType.POINT: "circle",
    LayerInfo.GeometryType.MULTIPOINT: "circle",
    LayerInfo.GeometryType.LINESTRING: "line",
    LayerInfo.GeometryType.MULTILINESTRING: "line",
    LayerInfo.GeometryType.POLYGON: "fill",
    LayerInfo.GeometryType.MULTIPOLYGON: "fill",
}
