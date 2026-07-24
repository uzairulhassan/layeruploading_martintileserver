from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import LayerShare


class IsOwnerOrSharedWithPermission(BasePermission):
    """Owners have full control. Users with an EDIT share can update style/labels/name.
    Users with a VIEW share get read-only access. Everyone else gets nothing.
    Only the owner may delete or (re)share a layer.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if obj.owner_id == user.id:
            return True

        share = LayerShare.objects.filter(layer=obj, shared_with=user).first()
        if share is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        if view.action in ("destroy", "share", "unshare"):
            return False

        return share.permission == LayerShare.Permission.EDIT
