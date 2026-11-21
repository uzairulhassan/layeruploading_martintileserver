"""Canonical application roles and helpers for assigning them."""
from django.contrib.auth.models import Permission

from .models import Role

ROLE_ADMIN = "Admin"
ROLE_USER = "User"

# Custom perms from LayerInfo / MapProject Meta.permissions.
CANONICAL_APP_PERMISSIONS = (
    ("layers", "upload_layerinfo"),
    ("layers", "share_layerinfo"),
    ("maps", "create_mapproject"),
    ("maps", "share_mapproject"),
)


def _permissions_for(pairs):
    perms = []
    for app_label, codename in pairs:
        perm = Permission.objects.filter(
            content_type__app_label=app_label,
            codename=codename,
        ).first()
        if perm is not None:
            perms.append(perm)
    return perms


def _ensure_role(name: str, description: str) -> Role:
    role, _ = Role.objects.get_or_create(name=name, defaults={"description": description})
    role.permissions.set(_permissions_for(CANONICAL_APP_PERMISSIONS))
    return role


def ensure_admin_role() -> Role:
    return _ensure_role(
        ROLE_ADMIN,
        "Full administrative access. Assigned to the bootstrap account.",
    )


def ensure_user_role() -> Role:
    return _ensure_role(ROLE_USER, "Standard application user.")
