from django.db.models import Sum
from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer
from apps.layers.models import LayerGroup, LayerInfo
from apps.layers.serializers import LayerInfoSerializer
from apps.layers.share_policy import validate_share_expires_at
from apps.layers.share_style import build_layer_paint_layers, build_style_legend

from .models import MapLayer, MapProject, MapShare, MapShareLink


class MapLayerSerializer(serializers.ModelSerializer):
    layer_detail = LayerInfoSerializer(source="layer", read_only=True)
    style_layers = serializers.SerializerMethodField()
    required_icons = serializers.SerializerMethodField()
    legend = serializers.SerializerMethodField()

    class Meta:
        model = MapLayer
        fields = [
            "id",
            "layer",
            "layer_detail",
            "order",
            "visible",
            "opacity",
            "style_override",
            "style_layers",
            "required_icons",
            "legend",
        ]
        read_only_fields = ["id", "style_layers", "required_icons", "legend"]

    def _paint_bundle(self, obj):
        cache = self.context.setdefault("_map_layer_paint", {})
        key = obj.pk
        if key not in cache:
            cache[key] = build_layer_paint_layers(
                layer=obj.layer,
                source_id=f"src-{obj.layer_id}",
                style=obj.style_override or {},
                opacity=obj.opacity,
                visibility="visible" if obj.visible else "none",
                id_prefix=f"layer-{obj.id}",
            )
        return cache[key]

    def get_style_layers(self, obj):
        layers, _needs_glyphs, _required_icons = self._paint_bundle(obj)
        return layers

    def get_required_icons(self, obj):
        _layers, _needs_glyphs, required_icons = self._paint_bundle(obj)
        return required_icons

    def get_legend(self, obj):
        """Same ``build_style_legend`` payload as external ``/m/`` styles."""
        cache = self.context.setdefault("_map_layer_legend", {})
        key = obj.pk
        if key not in cache:
            merged = {**(obj.layer.style or {}), **(obj.style_override or {})}
            cache[key] = build_style_legend(
                merged,
                title=obj.layer.name or "",
                geometry_type=obj.layer.geometry_type or "",
            )
        return cache[key]


class MapShareSerializer(serializers.ModelSerializer):
    shared_with_detail = UserSummarySerializer(source="shared_with", read_only=True)

    class Meta:
        model = MapShare
        fields = [
            "id", "map", "shared_with", "shared_with_detail",
            "permission", "created_at",
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
    """Add one ``layer``, or every layer of a KML/KMZ ``group`` (polygons → lines → points)."""

    layer = serializers.PrimaryKeyRelatedField(queryset=LayerInfo.objects.all(), required=False)
    group = serializers.PrimaryKeyRelatedField(queryset=LayerGroup.objects.all(), required=False)
    order = serializers.IntegerField(required=False)
    visible = serializers.BooleanField(required=False, default=True)
    opacity = serializers.FloatField(required=False, default=1.0)
    style_override = serializers.JSONField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if bool(attrs.get("layer")) == bool(attrs.get("group")):
            raise serializers.ValidationError("Send exactly one of 'layer' or 'group'.")
        return attrs


class ReorderMapLayersSerializer(serializers.Serializer):
    order = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class MapShareLinkSerializer(serializers.ModelSerializer):
    """External map share-link payload. ``style_url`` is the copyable Share URL."""

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
        return validate_share_expires_at(value)

    def _share_base(self, obj):
        request = self.context.get("request")
        base = request.build_absolute_uri("/") if request else "/"
        return f"{base.rstrip('/')}/m/{obj.token}"

    def get_style_url(self, obj):
        """Public Share URL (composition Style Spec) for this share token."""
        return f"{self._share_base(obj)}/style.json"

    def get_is_expired(self, obj):
        return obj.is_expired

    def get_never_expires(self, obj):
        return obj.expires_at is None

    def get_total_requests(self, obj):
        return obj.usage.aggregate(total=Sum("request_count"))["total"] or 0

    def get_layer_count(self, obj):
        """Visible layers only — matches what `/m/<token>/style.json` publishes."""
        return obj.map.map_layers.filter(visible=True).count()
