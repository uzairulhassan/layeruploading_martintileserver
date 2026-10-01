from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer

from .models import LayerInfo, LayerShare, LayerShareLink

# Map PostGIS geometry types → MapLibre / Mapbox style hints.
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

    def _tiles_base(self):
        """Absolute tiles base. MapLibre/Mapbox workers can't resolve relative tile URLs."""
        base = settings.TILES_PUBLIC_URL.rstrip("/")
        request = self.context.get("request")
        if base.startswith("/") and request is not None:
            base = request.build_absolute_uri(base)
        return base

    def get_tile_url(self, obj):
        """Martin function-source base (no z/x/y). Kept for API compatibility; prefer xyz_url."""
        return f"{self._tiles_base()}/{settings.MARTIN_LAYER_FUNCTION}"

    def get_xyz_url(self, obj):
        """Full XYZ template for the map builder. Requires sign-in (owner/shared user); use share links externally."""
        return f"{self.get_tile_url(obj)}/{{z}}/{{x}}/{{y}}?layer={obj.table_name}"

    def get_source_layer(self, obj):
        """MVT layer name inside each tile (layers_data.geolayers_tile names it after the table)."""
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


class LayerShareLinkSerializer(serializers.ModelSerializer):
    created_by_detail = UserSummarySerializer(source="created_by", read_only=True)
    xyz_url = serializers.SerializerMethodField()
    source_layer = serializers.SerializerMethodField()
    suggested_geometry = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    total_requests = serializers.SerializerMethodField()
    requests_last_30_days = serializers.SerializerMethodField()

    class Meta:
        model = LayerShareLink
        fields = [
            "id", "layer", "created_by_detail", "token", "xyz_url",
            "source_layer", "suggested_geometry", "expires_at",
            "is_blocked", "is_expired", "created_at",
            "last_used_at", "total_requests", "requests_last_30_days",
        ]
        read_only_fields = ["id", "token", "is_blocked", "created_at", "last_used_at"]
        extra_kwargs = {"layer": {"write_only": True}}

    def validate_expires_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Expiry must be in the future.")
        return value

    def get_xyz_url(self, obj):
        """Shareable, revocable XYZ template — proxied through serve_shared_tile, not Martin directly."""
        request = self.context.get("request")
        base = request.build_absolute_uri("/") if request else "/"
        return f"{base.rstrip('/')}/x/{obj.token}/{{z}}/{{x}}/{{y}}.pbf"

    def get_source_layer(self, obj):
        return obj.layer.table_name

    def get_suggested_geometry(self, obj):
        return _SUGGESTED_GEOMETRY.get(obj.layer.geometry_type, "line")

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_total_requests(self, obj):
        return obj.usage.aggregate(total=Sum("request_count"))["total"] or 0

    def get_requests_last_30_days(self, obj):
        since = timezone.localdate() - timedelta(days=30)
        return obj.usage.filter(date__gte=since).aggregate(total=Sum("request_count"))["total"] or 0


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
