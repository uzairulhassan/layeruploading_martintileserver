from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer

from .geometry_hints import SUGGESTED_GEOMETRY
from .models import LayerInfo, LayerShare, LayerShareLink


class LayerShareSerializer(serializers.ModelSerializer):
    shared_with_detail = UserSummarySerializer(source="shared_with", read_only=True)

    class Meta:
        model = LayerShare
        fields = [
            "id", "layer", "shared_with", "shared_with_detail",
            "permission", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"layer": {"write_only": True}}


class LayerInfoSerializer(serializers.ModelSerializer):
    owner_detail = UserSummarySerializer(source="owner", read_only=True)
    xyz_url = serializers.SerializerMethodField()
    source_layer = serializers.SerializerMethodField()
    my_permission = serializers.SerializerMethodField()
    shares = LayerShareSerializer(many=True, read_only=True)

    class Meta:
        model = LayerInfo
        fields = [
            "id", "name", "description", "owner", "owner_detail",
            "geometry_type", "srid", "feature_count", "bounds", "attribute_schema",
            "style", "label_config", "source_filename",
            "xyz_url", "source_layer",
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

    def get_xyz_url(self, obj):
        """Signed-in map-builder tile template; use share links for external access."""
        return (
            f"{self._tiles_base()}/{settings.MARTIN_LAYER_FUNCTION}"
            f"/{{z}}/{{x}}/{{y}}?layer={obj.table_name}"
        )

    def get_source_layer(self, obj):
        """MVT layer name inside each tile (named after the PostGIS table)."""
        return obj.table_name

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
    xyz_url = serializers.SerializerMethodField()
    style_url = serializers.SerializerMethodField()
    source_layer = serializers.SerializerMethodField()
    geometry_type = serializers.SerializerMethodField()
    suggested_geometry = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    never_expires = serializers.SerializerMethodField()
    total_requests = serializers.SerializerMethodField()

    class Meta:
        model = LayerShareLink
        fields = [
            "id", "layer", "token", "xyz_url", "style_url",
            "source_layer", "geometry_type", "suggested_geometry", "expires_at",
            "never_expires", "is_blocked", "is_expired", "created_at",
            "last_used_at", "total_requests",
        ]
        read_only_fields = ["id", "token", "is_blocked", "created_at", "last_used_at"]
        extra_kwargs = {
            "layer": {"write_only": True},
            "expires_at": {"required": False, "allow_null": True},
        }

    def validate_expires_at(self, value):
        if value is None:
            return value
        if value <= timezone.now():
            raise serializers.ValidationError("Expiry must be in the future.")
        return value

    def _share_base(self, obj):
        request = self.context.get("request")
        base = request.build_absolute_uri("/") if request else "/"
        return f"{base.rstrip('/')}/x/{obj.token}"

    def get_xyz_url(self, obj):
        """Shareable, revocable tile URL template — proxied through serve_shared_tile, not Martin directly."""
        return f"{self._share_base(obj)}/{{z}}/{{x}}/{{y}}.pbf"

    def get_style_url(self, obj):
        """Mapbox Style Spec for this share token (same auth / expiry / revoke as tiles)."""
        return f"{self._share_base(obj)}/style.json"

    def get_source_layer(self, obj):
        return obj.layer.table_name

    def get_geometry_type(self, obj):
        return obj.layer.geometry_type

    def get_suggested_geometry(self, obj):
        return SUGGESTED_GEOMETRY.get(obj.layer.geometry_type, "line")

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_never_expires(self, obj):
        return obj.expires_at is None

    def get_total_requests(self, obj):
        return obj.usage.aggregate(total=Sum("request_count"))["total"] or 0


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
