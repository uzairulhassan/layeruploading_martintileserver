from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.permissions import OWNER_DENY_FOR_SHAREES

from .models import MapShare


class IsMapOwnerOrSharedWithPermission(BasePermission):
    """Owners: full control. EDIT share: composition/layout. VIEW: read-only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if obj.owner_id == user.id:
            return True

        share = MapShare.objects.filter(map=obj, shared_with=user).first()
        if share is None:
            return False

        if request.method in SAFE_METHODS:
            return True

        if view.action in OWNER_DENY_FOR_SHAREES:
            return False

        return share.permission == MapShare.Permission.EDIT
