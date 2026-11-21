from rest_framework.permissions import BasePermission

# Owner-only mutations shared by layer / map object permissions.
OWNER_SHARE_ACTIONS = frozenset({"share", "unshare", "share_links", "revoke_share_link"})
OWNER_DENY_FOR_SHAREES = frozenset({"destroy"}) | OWNER_SHARE_ACTIONS


class CanManageRoles(BasePermission):
    """Staff, or users with accounts.* role-management permissions."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_staff or user.is_superuser:
            return True
        action_perm_map = {
            "list": "accounts.view_role",
            "retrieve": "accounts.view_role",
            "create": "accounts.add_role",
            "update": "accounts.change_role",
            "partial_update": "accounts.change_role",
            "destroy": "accounts.delete_role",
        }
        codename = action_perm_map.get(view.action)
        return bool(codename and user.has_role_permission(codename))


class _RequiresRolePermission(BasePermission):
    """Allow all actions except those listed, which need ``role_permission``."""

    role_permission = ""
    gated_actions = frozenset()

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if getattr(view, "action", None) not in self.gated_actions:
            return True
        return request.user.has_role_permission(self.role_permission)


class CanUploadLayers(_RequiresRolePermission):
    """Require ``layers.upload_layerinfo`` for layer create (upload)."""

    role_permission = "layers.upload_layerinfo"
    gated_actions = frozenset({"create"})


class CanShareLayers(_RequiresRolePermission):
    """Require ``layers.share_layerinfo`` for share / share-link actions."""

    role_permission = "layers.share_layerinfo"
    gated_actions = OWNER_SHARE_ACTIONS


class CanCreateMaps(_RequiresRolePermission):
    """Require ``maps.create_mapproject`` for map create."""

    role_permission = "maps.create_mapproject"
    gated_actions = frozenset({"create"})


class CanShareMaps(_RequiresRolePermission):
    """Require ``maps.share_mapproject`` for share / share-link actions."""

    role_permission = "maps.share_mapproject"
    gated_actions = OWNER_SHARE_ACTIONS
