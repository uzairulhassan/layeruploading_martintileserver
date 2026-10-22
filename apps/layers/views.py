from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import LayerInfo, LayerShare, LayerShareLink
from .permissions import IsOwnerOrSharedWithPermission
from .serializers import (
    LayerInfoSerializer,
    LayerShareLinkSerializer,
    LayerShareSerializer,
    LayerUploadSerializer,
)
from .services import ShapefileImportError, delete_layer, import_shapefile, sample_attribute_value


def _owner_forbidden(layer, user, detail="Only the owner can manage this layer."):
    if layer.owner_id == user.id:
        return None
    return Response({"detail": detail}, status=status.HTTP_403_FORBIDDEN)


class LayerViewSet(viewsets.ModelViewSet):
    serializer_class = LayerInfoSerializer
    permission_classes = [IsOwnerOrSharedWithPermission]

    def get_queryset(self):
        user = self.request.user
        return (
            LayerInfo.objects.filter(Q(owner=user) | Q(shares__shared_with=user))
            .distinct()
            .prefetch_related("shares")
            .select_related("owner")
        )

    def create(self, request, *args, **kwargs):
        upload_serializer = LayerUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        data = upload_serializer.validated_data

        try:
            layer = import_shapefile(
                owner=request.user,
                name=data["name"],
                description=data.get("description", ""),
                uploaded_file=data["file"],
            )
        except ShapefileImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = LayerInfoSerializer(layer, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

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
