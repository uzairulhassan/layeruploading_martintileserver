import uuid

from django.db.models import Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import CanShareLayers, CanUploadLayers
from apps.core.api_errors import ErrorCode, error_response

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
    delete_layer,
    delete_layer_group,
    distinct_attribute_values,
    import_shapefile,
)
from .share_style import build_layer_paint_layers


def visible_layers(user):
    """Layers ``user`` owns or has been shared."""
    return LayerInfo.objects.filter(Q(owner=user) | Q(shares__shared_with=user)).distinct()


def _owner_forbidden(request, layer, user, detail="Only the owner can manage this layer."):
    if layer.owner_id == user.id:
        return None
    return error_response(
        request,
        message=detail,
        code=ErrorCode.PERMISSION_DENIED,
        status_code=status.HTTP_403_FORBIDDEN,
    )


class LayerViewSet(viewsets.ModelViewSet):
    serializer_class = LayerInfoSerializer
    permission_classes = [IsOwnerOrSharedWithPermission, CanUploadLayers, CanShareLayers]

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
            "description": data["description"],
            "uploaded_file": data["file"],
        }
        context = self.get_serializer_context()

        # PublicError / LayerImportError → global handler (safe body, no ogr2ogr stderr).
        if is_kml_upload(data["file"].name):
            group = import_kml(**upload_kwargs)
            payload = {"group": LayerGroupSerializer(group, context=context).data}
        else:
            layer = import_shapefile(**upload_kwargs)
            payload = LayerInfoSerializer(layer, context=context).data

        return Response(payload, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        delete_layer(instance)

    @action(detail=True, methods=["get"], url_path="attribute-values")
    def attribute_values(self, request, pk=None):
        """Distinct attribute values for categorical color/icon styling."""
        layer = self.get_object()
        field = (request.query_params.get("field") or "").strip()
        if not field:
            return error_response(
                request,
                message="Query parameter 'field' is required.",
                code=ErrorCode.VALIDATION_ERROR,
            )
        try:
            limit = int(request.query_params.get("limit") or 40)
        except (TypeError, ValueError):
            limit = 40
        values = distinct_attribute_values(layer, field, limit=limit)
        return Response({"field": field, "values": values, "count": len(values)})

    @action(detail=True, methods=["post"], url_path="preview-style")
    def preview_style(self, request, pk=None):
        """Draft MapLibre paint layers for the style modal (not yet saved)."""
        layer = self.get_object()
        draft_style = request.data.get("style")
        draft_labels = request.data.get("label_config")
        if not isinstance(draft_style, dict):
            draft_style = {}
        if not isinstance(draft_labels, dict):
            draft_labels = {}

        source_id = f"preview-src-{layer.id}"
        paint_layers, _, required_icons = build_layer_paint_layers(
            layer=layer,
            source_id=source_id,
            style=draft_style,
            label_config=draft_labels,
            id_prefix=f"preview-{layer.id}",
            replace_style=True,
            replace_label_config=True,
        )
        tile_info = LayerInfoSerializer(layer, context=self.get_serializer_context()).data
        return Response(
            {
                "source_id": source_id,
                "xyz_url": tile_info.get("xyz_url"),
                "bounds": layer.bounds,
                "style_layers": paint_layers,
                "required_icons": required_icons,
            }
        )

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        layer = self.get_object()
        if denied := _owner_forbidden(request, layer, request.user, "Only the owner can share this layer."):
            return denied

        serializer = LayerShareSerializer(data={**request.data, "layer": layer.id})
        serializer.is_valid(raise_exception=True)

        shared_with = serializer.validated_data["shared_with"]
        if shared_with.id == layer.owner_id:
            return error_response(
                request,
                message="Cannot share a layer with its owner.",
                code=ErrorCode.BAD_REQUEST,
            )

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
        if denied := _owner_forbidden(request, layer, request.user, "Only the owner can modify sharing."):
            return denied

        user_id = request.data.get("user_id")
        deleted, _ = LayerShare.objects.filter(layer=layer, shared_with_id=user_id).delete()
        if not deleted:
            return error_response(
                request,
                message="Share not found.",
                code=ErrorCode.NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="share-links")
    def share_links(self, request, pk=None):
        """List or create revocable external share links for this layer."""
        layer = self.get_object()
        if denied := _owner_forbidden(
            request, layer, request.user, "Only the owner can manage external share links."
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
            request, layer, request.user, "Only the owner can manage external share links."
        ):
            return denied

        deleted, _ = LayerShareLink.objects.filter(id=link_id, layer=layer).delete()
        if not deleted:
            return error_response(
                request,
                message="Share link not found.",
                code=ErrorCode.NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
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
    permission_classes = [IsGroupOwnerOrViewerPermission, CanShareLayers]

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

    def _group_owner_forbidden(self, request, group, detail="Only the owner can manage this group."):
        if group.owner_id == request.user.id:
            return None
        return error_response(
            request,
            message=detail,
            code=ErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Share every layer in the group with one user."""
        group = self.get_object()
        if denied := self._group_owner_forbidden(request, group, "Only the owner can share this group."):
            return denied
        serializer = LayerGroupShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shared_with = serializer.validated_data["shared_with"]
        if shared_with.id == group.owner_id:
            return error_response(
                request,
                message="Cannot share a group with its owner.",
                code=ErrorCode.BAD_REQUEST,
            )

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
        if denied := self._group_owner_forbidden(request, group, "Only the owner can modify sharing."):
            return denied
        deleted, _ = LayerShare.objects.filter(layer__group=group, shared_with_id=request.data.get("user_id")).delete()
        if not deleted:
            return error_response(
                request,
                message="Share not found.",
                code=ErrorCode.NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
