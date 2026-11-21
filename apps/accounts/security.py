"""Login lockout and JWT refresh-token revocation helpers."""
from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def _lockout_seconds() -> int:
    return settings.AUTH_LOGIN_LOCKOUT_SECONDS


def _lockout_max_attempts() -> int:
    return settings.AUTH_LOGIN_LOCKOUT_ATTEMPTS


def _lockout_cache_key(*, client_ip: str, identifier: str) -> str:
    normalized = (identifier or "").strip().lower()
    digest = hashlib.sha256(f"{client_ip}|{normalized}".encode("utf-8")).hexdigest()[:32]
    return f"geolayers:auth:fail:{digest}"


def client_ip_from_request(request) -> str:
    """Client IP for lockout keys.

    Prefer ``X-Real-IP`` (Nginx sets this to ``$remote_addr``). Do not trust the
    first ``X-Forwarded-For`` hop — clients can spoof it and weaken lockout.
    """
    real_ip = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if real_ip:
        return real_ip
    return (request.META.get("REMOTE_ADDR") or "").strip() or "unknown"


def is_login_locked(*, client_ip: str, identifier: str) -> bool:
    return cache.get(_lockout_cache_key(client_ip=client_ip, identifier=identifier)) == "locked"


def register_failed_login(*, client_ip: str, identifier: str) -> int:
    """Increment failure count; lock when the threshold is reached. Returns the count."""
    key = _lockout_cache_key(client_ip=client_ip, identifier=identifier)
    if cache.get(key) == "locked":
        return _lockout_max_attempts()

    count_key = f"{key}:count"
    try:
        count = cache.incr(count_key)
    except ValueError:
        cache.set(count_key, 1, _lockout_seconds())
        count = 1

    if count >= _lockout_max_attempts():
        cache.set(key, "locked", _lockout_seconds())
        cache.delete(count_key)
    return count


def clear_failed_logins(*, client_ip: str, identifier: str) -> None:
    key = _lockout_cache_key(client_ip=client_ip, identifier=identifier)
    cache.delete(key)
    cache.delete(f"{key}:count")


def blacklist_user_refresh_tokens(user) -> int:
    """Blacklist every outstanding refresh token for ``user``. Returns how many were newly blacklisted."""
    if user is None or not getattr(user, "pk", None):
        return 0
    blacklisted = 0
    for outstanding in OutstandingToken.objects.filter(user_id=user.pk):
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding)
        if created:
            blacklisted += 1
    return blacklisted
