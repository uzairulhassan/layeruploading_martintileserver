"""Share-link policy helpers (capability URLs; revoke/block/expiry remain the controls)."""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers


def generate_share_token() -> str:
    """URL-safe token (~256 bits). Length fits ``CharField(max_length=64)``."""
    return secrets.token_urlsafe(32)


def share_link_max_ttl() -> timedelta:
    days = max(1, int(getattr(settings, "SHARE_LINK_MAX_TTL_DAYS", 365) or 365))
    return timedelta(days=days)


def validate_share_expires_at(value):
    """``None`` = never expires (still revocable). Finite values must be within max TTL."""
    if value is None:
        return value
    now = timezone.now()
    if value <= now:
        raise serializers.ValidationError("Expiry must be in the future.")
    max_ttl = share_link_max_ttl()
    if value > now + max_ttl:
        raise serializers.ValidationError(
            f"Expiry cannot be more than {max_ttl.days} days from now."
        )
    return value
