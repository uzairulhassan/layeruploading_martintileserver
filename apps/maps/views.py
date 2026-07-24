from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.layers.models import LayerInfo

from .models import MapLayer, MapProject, MapShare
from .permissions import IsMapOwnerOrSharedWithPermission
from .serializers import (
    AddMapLayerSerializer,
    MapLayerSerializer,
    MapProjectSerializer,
    MapShareSerializer,
    ReorderMapLayersSerializer,
)


class MapProjectViewSet(viewsets.ModelViewSet):
    serializer_class = MapProjectSerializer
    permission_classes = [IsMapOwnerOrSharedWithPermission]

    def get_queryset(self):
        user = self.request.user
        return (
            MapProject.objects.filter(Q(owner=user) | Q(shares__shared_with=user))
            .distinct()
            .select_related("owner")
            .prefetch_related("map_layers__layer", "shares")
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _accessible_layers(self, user):
        return LayerInfo.objects.filter(Q(owner=user) | Q(shares__shared_with=user)).distinct()

    @action(detail=True, methods=["get", "post"], url_path="layers")
    def layers_collection(self, request, pk=None):
        map_project = self.get_object()

        if request.method == "GET":
            qs = map_project.map_layers.select_related("layer")
            return Response(MapLayerSerializer(qs, many=True).data)

        serializer = AddMapLayerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        layer = serializer.validated_data["layer"]

        if not self._accessible_layers(request.user).filter(id=layer.id).exists():
            return Response(
                {"detail": "You do not have access to this layer."}, status=status.HTTP_403_FORBIDDEN
            )

        order = serializer.validated_data.get("order")
        if order is None:
            max_order = map_project.map_layers.count()
            order = max_order

        map_layer, _ = MapLayer.objects.update_or_create(
            map=map_project,
            layer=layer,
            defaults={
                "order": order,
                "visible": serializer.validated_data.get("visible", True),
                "opacity": serializer.validated_data.get("opacity", 1.0),
                "style_override": serializer.validated_data.get("style_override"),
            },
        )
        return Response(MapLayerSerializer(map_layer).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"layers/(?P<map_layer_id>[^/.]+)")
    def layer_detail(self, request, pk=None, map_layer_id=None):
        map_project = self.get_object()
        map_layer = map_project.map_layers.filter(id=map_layer_id).first()
        if map_layer is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "DELETE":
            map_layer.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        for field in ("order", "visible", "opacity", "style_override"):
            if field in request.data:
                setattr(map_layer, field, request.data[field])
        map_layer.save()
        return Response(MapLayerSerializer(map_layer).data)

    @action(detail=True, methods=["post"], url_path="reorder")
    def reorder(self, request, pk=None):
        map_project = self.get_object()
        serializer = ReorderMapLayersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        id_to_order = {map_layer_id: idx for idx, map_layer_id in enumerate(serializer.validated_data["order"])}
        map_layers = list(map_project.map_layers.filter(id__in=id_to_order.keys()))
        for map_layer in map_layers:
            map_layer.order = id_to_order[map_layer.id]
        MapLayer.objects.bulk_update(map_layers, ["order"])

        qs = map_project.map_layers.select_related("layer")
        return Response(MapLayerSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        map_project = self.get_object()
        if map_project.owner_id != request.user.id:
            return Response({"detail": "Only the owner can share this map."}, status=status.HTTP_403_FORBIDDEN)

        serializer = MapShareSerializer(data={**request.data, "map": map_project.id})
        serializer.is_valid(raise_exception=True)

        shared_with = serializer.validated_data["shared_with"]
        if shared_with.id == map_project.owner_id:
            return Response({"detail": "Cannot share a map with its owner."}, status=status.HTTP_400_BAD_REQUEST)

        share, _ = MapShare.objects.update_or_create(
            map=map_project,
            shared_with=shared_with,
            defaults={
                "permission": serializer.validated_data.get("permission", MapShare.Permission.VIEW),
                "shared_by": request.user,
            },
        )
        return Response(MapShareSerializer(share).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def unshare(self, request, pk=None):
        map_project = self.get_object()
        if map_project.owner_id != request.user.id:
            return Response({"detail": "Only the owner can modify sharing."}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get("user_id")
        deleted, _ = MapShare.objects.filter(map=map_project, shared_with_id=user_id).delete()
        if not deleted:
            return Response({"detail": "Share not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
