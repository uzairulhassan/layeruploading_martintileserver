from django.contrib.auth.models import AbstractUser, Permission
from django.db import models


class Role(models.Model):
    """A named bundle of permissions that can be assigned to users.

    Roles wrap Django's built-in Permission objects so admins can compose
    custom roles (e.g. "GIS Editor", "Viewer") from the same fine-grained
    permissions (including the custom ones declared on Layer/Map models).
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user model so roles/profile fields can grow independently of auth.User."""

    email = models.EmailField(unique=True)
    roles = models.ManyToManyField(Role, blank=True, related_name="users")
    organization = models.CharField(max_length=150, blank=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.get_full_name() or self.username

    def has_role_permission(self, codename: str) -> bool:
        """Check permission granted directly OR via any assigned role."""
        if self.is_superuser:
            return True
        if self.has_perm(codename):
            return True
        app_label, _, perm_codename = codename.partition(".")
        qs = self.roles.filter(permissions__content_type__app_label=app_label,
                                permissions__codename=perm_codename)
        return qs.exists()
