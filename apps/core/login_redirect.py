"""Post-login return paths for GeoLayers HTML pages.

Home uses a clean `/login/`. Deep links keep a safe `?next=…` (Django's
`REDIRECT_FIELD_NAME`) and are honored after sign-in.
"""

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

DEFAULT_POST_LOGIN_PATH = "/"


def _path_only(value: str) -> str:
    return value.split("?", 1)[0]


def _is_home(path: str | None) -> bool:
    if not path:
        return True
    return _path_only(path.strip()) in ("", "/")


def _is_safe_internal(path: str | None) -> bool:
    if not path or not isinstance(path, str):
        return False
    candidate = path.strip()
    return bool(candidate) and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts=None
    )


def should_keep_next(path: str | None) -> bool:
    """True when `?next=` is a safe deep link worth keeping / honoring."""
    return _is_safe_internal(path) and not _is_home(path)


def resolve_post_login_path(raw: str | None, default: str = DEFAULT_POST_LOGIN_PATH) -> str:
    if not should_keep_next(raw):
        return default
    return raw.strip()


class GeoLayersLoginRequiredMixin(LoginRequiredMixin):
    """Omits `?next=/` for home; keeps a safe `?next=` for deep links."""

    login_url = "core:login"
    redirect_field_name = REDIRECT_FIELD_NAME

    def handle_no_permission(self):
        path = self.request.get_full_path()
        login_url = resolve_url(self.get_login_url())
        if _is_home(path):
            return redirect(login_url)
        return redirect_to_login(path, login_url, self.get_redirect_field_name())
