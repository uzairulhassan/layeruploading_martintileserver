from rest_framework.permissions import BasePermission


class CanManageRoles(BasePermission):
    """Only staff or users holding the accounts.* role-management permissions."""

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
