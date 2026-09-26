from datetime import timedelta

from django.contrib.auth.models import AbstractUser, Permission
from django.db import models
from django.utils import timezone

PROFILE_CHANGE_COOLDOWN = timedelta(days=30)


def user_avatar_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/{instance.pk}/{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"


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
    avatar = models.ImageField(upload_to=user_avatar_upload_to, blank=True, null=True)
    username_changed_at = models.DateTimeField(null=True, blank=True)
    email_changed_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def account_type(self) -> str:
        if self.is_superuser or self.is_staff or self.roles.filter(name="Admin").exists():
            return "Admin"
        return "User"

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None

    def _can_change_identity(self, last_changed_at):
        if last_changed_at is None:
            return True
        return timezone.now() >= last_changed_at + PROFILE_CHANGE_COOLDOWN

    def _next_change_at(self, last_changed_at):
        if last_changed_at is None:
            return None
        return last_changed_at + PROFILE_CHANGE_COOLDOWN

    @property
    def can_change_username(self) -> bool:
        return self._can_change_identity(self.username_changed_at)

    @property
    def can_change_email(self) -> bool:
        return self._can_change_identity(self.email_changed_at)

    @property
    def next_username_change_at(self):
        return self._next_change_at(self.username_changed_at)

    @property
    def next_email_change_at(self):
        return self._next_change_at(self.email_changed_at)

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
