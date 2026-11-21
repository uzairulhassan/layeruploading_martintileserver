from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_canonical_roles(sender, **kwargs):
    from .roles import ensure_admin_role, ensure_user_role

    ensure_user_role()
    ensure_admin_role()


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts & Roles"

    def ready(self):
        post_migrate.connect(_sync_canonical_roles, sender=self)
