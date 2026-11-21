from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.permissions import OWNER_DENY_FOR_SHAREES

from .models import LayerShare


class IsOwnerOrSharedWithPermission(BasePermission):
    """Owners: full control. EDIT share: style/labels/name. VIEW: read-only."""

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

        if view.action in OWNER_DENY_FOR_SHAREES:
            return False

        return share.permission == LayerShare.Permission.EDIT


class IsGroupOwnerOrViewerPermission(BasePermission):
    """Group owner manages the group; users with any child-layer share can read."""

    OWNER_ONLY_ACTIONS = frozenset(
        {"destroy", "update", "partial_update", "share", "unshare"}
    )

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if obj.owner_id == request.user.id:
            return True
        if getattr(view, "action", None) in self.OWNER_ONLY_ACTIONS:
            return False
        return request.method in SAFE_METHODS
