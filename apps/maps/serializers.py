from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer
from apps.layers.models import LayerInfo
from apps.layers.serializers import LayerInfoSerializer

from .models import MapLayer, MapProject, MapShare, MapShareLink


class MapLayerSerializer(serializers.ModelSerializer):
    layer_detail = LayerInfoSerializer(source="layer", read_only=True)

    class Meta:
        model = MapLayer
        fields = ["id", "layer", "layer_detail", "order", "visible", "opacity", "style_override"]
        read_only_fields = ["id"]


class MapShareSerializer(serializers.ModelSerializer):
    shared_with_detail = UserSummarySerializer(source="shared_with", read_only=True)
    shared_by_detail = UserSummarySerializer(source="shared_by", read_only=True)

    class Meta:
        model = MapShare
        fields = [
            "id", "map", "shared_with", "shared_with_detail",
            "shared_by_detail", "permission", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"map": {"write_only": True}}


class MapProjectSerializer(serializers.ModelSerializer):
    owner_detail = UserSummarySerializer(source="owner", read_only=True)
    my_permission = serializers.SerializerMethodField()
    map_layers = MapLayerSerializer(many=True, read_only=True)
    shares = MapShareSerializer(many=True, read_only=True)

    class Meta:
        model = MapProject
        fields = [
            "id", "name", "description", "owner", "owner_detail",
            "basemap_style", "center_lng", "center_lat", "zoom",
            "map_layers", "shares", "my_permission", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def get_my_permission(self, obj):
        request = self.context.get("request")
        if request is None:
            return None
        user = request.user
        if obj.owner_id == user.id:
            return "owner"
        share = next((s for s in obj.shares.all() if s.shared_with_id == user.id), None)
        return share.permission if share else None


class AddMapLayerSerializer(serializers.Serializer):
    layer = serializers.PrimaryKeyRelatedField(queryset=LayerInfo.objects.all())
    order = serializers.IntegerField(required=False)
    visible = serializers.BooleanField(required=False, default=True)
    opacity = serializers.FloatField(required=False, default=1.0)
    style_override = serializers.JSONField(required=False, allow_null=True, default=None)


class ReorderMapLayersSerializer(serializers.Serializer):
    order = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class MapShareLinkSerializer(serializers.ModelSerializer):
    """External Map URL payload. ``style_url`` is what the UI copies as the Map URL."""

    style_url = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    never_expires = serializers.SerializerMethodField()
    total_requests = serializers.SerializerMethodField()
    layer_count = serializers.SerializerMethodField()

    class Meta:
        model = MapShareLink
        fields = [
            "id",
            "map",
            "token",
            "style_url",
            "layer_count",
            "expires_at",
            "never_expires",
            "is_blocked",
            "is_expired",
            "created_at",
            "last_used_at",
            "total_requests",
        ]
        read_only_fields = ["id", "token", "is_blocked", "created_at", "last_used_at"]
        extra_kwargs = {
            "map": {"write_only": True},
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
        return f"{base.rstrip('/')}/m/{obj.token}"

    def get_style_url(self, obj):
        """Map URL — full composition Style Spec for this share token."""
        return f"{self._share_base(obj)}/style.json"

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_never_expires(self, obj):
        return obj.expires_at is None

    def get_total_requests(self, obj):
        return obj.usage.aggregate(total=Sum("request_count"))["total"] or 0

    def get_layer_count(self, obj):
        return obj.map.map_layers.count()
