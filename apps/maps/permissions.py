from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import MapShare


class IsMapOwnerOrSharedWithPermission(BasePermission):
    """Same shape as the layers permission: owner has full control, EDIT shares can
    modify layer composition/layout, VIEW shares are read-only, others get nothing.
    Only the owner may delete or (re)share a map.
    """

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

        if view.action in ("destroy", "share", "unshare"):
            return False

        return share.permission == MapShare.Permission.EDIT
