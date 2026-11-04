import uuid

from django.db.models import Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .kml_import import import_kml, is_kml_upload
from .models import LayerGroup, LayerInfo, LayerShare, LayerShareLink
from .permissions import IsGroupOwnerOrViewerPermission, IsOwnerOrSharedWithPermission
from .serializers import (
    LayerGroupSerializer,
    LayerGroupShareSerializer,
    LayerInfoSerializer,
    LayerShareLinkSerializer,
    LayerShareSerializer,
    LayerUploadSerializer,
)
from .services import (
    LayerImportError,
    delete_layer,
    delete_layer_group,
    import_shapefile,
    sample_attribute_value,
)


def visible_layers(user):
    """Layers ``user`` owns or has been shared."""
    return LayerInfo.objects.filter(Q(owner=user) | Q(shares__shared_with=user)).distinct()


def _owner_forbidden(layer, user, detail="Only the owner can manage this layer."):
    if layer.owner_id == user.id:
        return None
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


class LayerViewSet(viewsets.ModelViewSet):
    serializer_class = LayerInfoSerializer
    permission_classes = [IsOwnerOrSharedWithPermission]

    def get_queryset(self):
        qs = (
            visible_layers(self.request.user)
            .prefetch_related("shares")
            .select_related("owner", "group")
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            try:
                qs = qs.filter(group_id=uuid.UUID(group_id))
            except ValueError:
                qs = qs.none()
        return qs

    def create(self, request, *args, **kwargs):
        """Shapefile .zip → one layer. KML/KMZ → a group with one layer per geometry type."""
        upload_serializer = LayerUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        data = upload_serializer.validated_data
        upload_kwargs = {
            "owner": request.user,
            "name": data["name"],
            "description": data.get("description", ""),
            "uploaded_file": data["file"],
        }
        context = self.get_serializer_context()

        try:
            if is_kml_upload(data["file"].name):
                group = import_kml(**upload_kwargs)
                payload = {"group": LayerGroupSerializer(group, context=context).data}
            else:
                layer = import_shapefile(**upload_kwargs)
                payload = LayerInfoSerializer(layer, context=context).data
        except LayerImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payload, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        delete_layer(instance)

    @action(detail=True, methods=["get"], url_path="sample-attribute")
    def sample_attribute(self, request, pk=None):
        """One real attribute value for the style modal live preview."""
        layer = self.get_object()
        field = (request.query_params.get("field") or "").strip()
        if not field:
            return Response({"detail": "Query parameter 'field' is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            value = sample_attribute_value(layer, field)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"field": field, "value": value})

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        layer = self.get_object()
        if denied := _owner_forbidden(layer, request.user, "Only the owner can share this layer."):
            return denied

        serializer = LayerShareSerializer(data={**request.data, "layer": layer.id})
        serializer.is_valid(raise_exception=True)

        shared_with = serializer.validated_data["shared_with"]
        if shared_with.id == layer.owner_id:
            return Response({"detail": "Cannot share a layer with its owner."}, status=status.HTTP_400_BAD_REQUEST)

        share, _ = LayerShare.objects.update_or_create(
            layer=layer,
            shared_with=shared_with,
            defaults={
                "permission": serializer.validated_data.get("permission", LayerShare.Permission.VIEW),
                "shared_by": request.user,
            },
        )
        return Response(LayerShareSerializer(share).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def unshare(self, request, pk=None):
        layer = self.get_object()
        if denied := _owner_forbidden(layer, request.user, "Only the owner can modify sharing."):
            return denied

        user_id = request.data.get("user_id")
        deleted, _ = LayerShare.objects.filter(layer=layer, shared_with_id=user_id).delete()
        if not deleted:
            return Response({"detail": "Share not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="share-links")
    def share_links(self, request, pk=None):
        """List or create revocable external share links for this layer."""
        layer = self.get_object()
        if denied := _owner_forbidden(
            layer, request.user, "Only the owner can manage external share links."
        ):
            return denied

        if request.method == "GET":
            links = layer.share_links.all()
            return Response(LayerShareLinkSerializer(links, many=True, context=self.get_serializer_context()).data)

        serializer = LayerShareLinkSerializer(
            data={**request.data, "layer": layer.id}, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"share-links/(?P<link_id>[0-9a-f-]+)")
    def revoke_share_link(self, request, pk=None, link_id=None):
        layer = self.get_object()
        if denied := _owner_forbidden(
            layer, request.user, "Only the owner can manage external share links."
        ):
            return denied

        deleted, _ = LayerShareLink.objects.filter(id=link_id, layer=layer).delete()
        if not deleted:
            return Response({"detail": "Share link not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LayerGroupViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """KML/KMZ uploads as one unit. Groups are created only by uploading (POST /api/layers/)."""

    serializer_class = LayerGroupSerializer
    permission_classes = [IsGroupOwnerOrViewerPermission]

    def get_queryset(self):
        user = self.request.user
        child_layers = visible_layers(user).select_related("owner", "group").prefetch_related("shares")
        return (
            LayerGroup.objects.filter(Q(owner=user) | Q(layers__shares__shared_with=user))
            .distinct()
            .select_related("owner")
            .prefetch_related(Prefetch("layers", queryset=child_layers))
        )

    def perform_destroy(self, instance):
        delete_layer_group(instance)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Share every layer in the group with one user."""
        group = self.get_object()
        serializer = LayerGroupShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shared_with = serializer.validated_data["shared_with"]
        if shared_with.id == group.owner_id:
            return Response({"detail": "Cannot share a group with its owner."}, status=status.HTTP_400_BAD_REQUEST)

        permission = serializer.validated_data["permission"]
        layers = list(LayerInfo.objects.filter(group=group))
        for layer in layers:
            LayerShare.objects.update_or_create(
                layer=layer,
                shared_with=shared_with,
                defaults={"permission": permission, "shared_by": request.user},
            )
        return Response(
            {"shared_with": shared_with.id, "permission": permission, "layer_count": len(layers)},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def unshare(self, request, pk=None):
        """Remove one user's access to every layer in the group."""
        group = self.get_object()
        deleted, _ = LayerShare.objects.filter(layer__group=group, shared_with_id=request.data.get("user_id")).delete()
        if not deleted:
            return Response({"detail": "Share not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
