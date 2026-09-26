"""Canonical application roles and helpers for assigning them."""
from .models import Role

ROLE_ADMIN = "Admin"
ROLE_USER = "User"


def ensure_admin_role() -> Role:
    role, _ = Role.objects.get_or_create(
        name=ROLE_ADMIN,
        defaults={"description": "Full administrative access. Assigned to the bootstrap account."},
    )
    return role


def ensure_user_role() -> Role:
    role, _ = Role.objects.get_or_create(
        name=ROLE_USER,
        defaults={"description": "Standard application user."},
    )
    return role
