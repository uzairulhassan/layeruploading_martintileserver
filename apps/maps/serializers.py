from rest_framework import serializers

from apps.accounts.serializers import UserSummarySerializer
from apps.layers.models import LayerInfo
from apps.layers.serializers import LayerInfoSerializer

from .models import MapLayer, MapProject, MapShare


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
