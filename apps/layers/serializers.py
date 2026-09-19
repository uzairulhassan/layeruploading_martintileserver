from django.conf import settings
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer

from .models import LayerInfo, LayerShare

# Map PostGIS geometry types → GeoTrak / MapLibre style hints.
_SUGGESTED_GEOMETRY = {
    LayerInfo.GeometryType.POINT: "circle",
    LayerInfo.GeometryType.MULTIPOINT: "circle",
    LayerInfo.GeometryType.LINESTRING: "line",
    LayerInfo.GeometryType.MULTILINESTRING: "line",
    LayerInfo.GeometryType.POLYGON: "fill",
    LayerInfo.GeometryType.MULTIPOLYGON: "fill",
}


class LayerShareSerializer(serializers.ModelSerializer):
    shared_with_detail = UserSummarySerializer(source="shared_with", read_only=True)
    shared_by_detail = UserSummarySerializer(source="shared_by", read_only=True)

    class Meta:
        model = LayerShare
        fields = [
            "id", "layer", "shared_with", "shared_with_detail",
            "shared_by_detail", "permission", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"layer": {"write_only": True}}


class LayerInfoSerializer(serializers.ModelSerializer):
    owner_detail = UserSummarySerializer(source="owner", read_only=True)
    tile_url = serializers.SerializerMethodField()
    xyz_url = serializers.SerializerMethodField()
    source_layer = serializers.SerializerMethodField()
    suggested_geometry = serializers.SerializerMethodField()
    my_permission = serializers.SerializerMethodField()
    shares = LayerShareSerializer(many=True, read_only=True)

    class Meta:
        model = LayerInfo
        fields = [
            "id", "name", "description", "owner", "owner_detail",
            "geometry_type", "srid", "feature_count", "bounds", "attribute_schema",
            "style", "label_config", "source_filename", "tile_url",
            "xyz_url", "source_layer", "suggested_geometry",
            "my_permission", "shares", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "owner", "geometry_type", "srid", "feature_count", "bounds",
            "attribute_schema", "source_filename", "created_at", "updated_at",
        ]

    def get_tile_url(self, obj):
        """Martin source base (no z/x/y). Used by the built-in map builder."""
        return f"{settings.MARTIN_TILE_SERVER_URL.rstrip('/')}/{obj.table_name}"

    def get_xyz_url(self, obj):
        """Shareable XYZ template for external map clients (e.g. GeoTrak)."""
        return f"{self.get_tile_url(obj)}/{{z}}/{{x}}/{{y}}"

    def get_source_layer(self, obj):
        """Martin / MapLibre source-layer id (PostGIS table name)."""
        return obj.table_name

    def get_suggested_geometry(self, obj):
        return _SUGGESTED_GEOMETRY.get(obj.geometry_type, "line")

    def get_my_permission(self, obj):
        request = self.context.get("request")
        if request is None:
            return None
        user = request.user
        if obj.owner_id == user.id:
            return "owner"
        share = next((s for s in obj.shares.all() if s.shared_with_id == user.id), None)
        return share.permission if share else None


class LayerUploadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.lower().endswith(".zip"):
            raise serializers.ValidationError("Upload a .zip archive containing the shapefile (.shp/.shx/.dbf/.prj).")
        if value.size > settings.MAX_SHAPEFILE_UPLOAD_SIZE:
            max_mb = settings.MAX_SHAPEFILE_UPLOAD_SIZE // (1024 * 1024)
            raise serializers.ValidationError(f"File exceeds the {max_mb}MB upload limit.")
        return value
