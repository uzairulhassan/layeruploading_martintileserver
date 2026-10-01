"""Tile authorization for the shared Nginx (``auth_request``) and the dev-only Django proxy.

Nginx on :8081 sends a subrequest to ``validate_tile_request`` for two kinds of tile URL:

* ``/tiles/geolayers_tile/{z}/{x}/{y}?layer=layer_<hex>``  - the app's own map builder.
  Allowed for the layer owner, users it is shared with, and superusers. They are
  identified by the Django session cookie or a ``Bearer`` JWT.
* ``/x/<share-token>/{z}/{x}/{y}.pbf``  - revocable, expiring public share links
  (``LayerShareLink``). No account is needed; the token is checked on every tile.

On success Django returns 204 plus ``X-Tile-Layer: <table>``, and Nginx proxies
to Martin with *that* table. The client's own ``?layer=`` is never trusted.
Refusals return 401/403 with ``X-Tile-Deny-Reason``, which Nginx turns into
404 / 410 / 403 for share links.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import LayerInfo, LayerShare, LayerShareLink, LayerShareLinkUsage

logger = logging.getLogger(__name__)

# Keep in sync with geo-infra/nginx/templates/geolayers.conf.template
SHARE_TILE_RE = re.compile(r"^/x/(?P<token>[A-Za-z0-9_-]+)/\d+/\d+/\d+\.pbf$")
APP_TILE_RE = re.compile(r"^/tiles/(?P<source>[A-Za-z0-9_]+)/\d+/\d+/\d+(?:\.pbf|\.mvt)?$")
LAYER_TABLE_RE = re.compile(r"^layer_[0-9a-f]{32}$")
LAST_USED_RESOLUTION = timedelta(seconds=60)

# Share-link refusal codes -> HTTP status the client sees (Nginx maps the same codes).
SHARE_DENY_STATUS = {"not_found": 404, "blocked": 403, "expired": 410}
SHARE_DENY_MESSAGE = {
    "not_found": "Share link not found.",
    "blocked": "This share link has been blocked.",
    "expired": "This share link has expired.",
}


@dataclass(frozen=True)
class TileDecision:
    status: int  # 204 allow, 401 sign-in required, 403 refused
    reason: str = ""  # X-Tile-Deny-Reason
    layer_table: str = ""  # X-Tile-Layer (only when allowed)
    token_label: str = "-"  # logged by Nginx as tile_token=...


# ---------------------------------------------------------------- share links
def check_share_link(token: str) -> tuple[LayerShareLink | None, str]:
    """Return ``(link, "")`` when usable, else ``(None|link, deny_code)``."""
    link = LayerShareLink.objects.select_related("layer").filter(token=token).first()
    if link is None:
        return None, "not_found"
    if link.is_blocked:
        return link, "blocked"
    if link.is_expired:
        return link, "expired"
    return link, ""


def record_share_link_usage(link: LayerShareLink) -> None:
    """One atomic upsert per tile, plus a throttled last_used_at. Never blocks tiles."""
    now = timezone.now()
    table = LayerShareLinkUsage._meta.db_table
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {table} (link_id, date, request_count, last_request_at)
                VALUES (%s, %s, 1, %s)
                ON CONFLICT ON CONSTRAINT layer_share_link_usage_unique
                DO UPDATE SET request_count = {table}.request_count + 1,
                              last_request_at = EXCLUDED.last_request_at
                """,
                [link.pk, timezone.localdate(now), now],
            )
        if link.last_used_at is None or now - link.last_used_at >= LAST_USED_RESOLUTION:
            LayerShareLink.objects.filter(pk=link.pk).update(last_used_at=now)
    except Exception:  # pragma: no cover - logging must not take tiles down
        logger.exception("Could not record usage for share link %s", link.pk)


# ---------------------------------------------------------------- signed-in users
def _request_user(request):
    """Session user, else a valid ``Authorization: Bearer <JWT>`` user, else None."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication

        result = JWTAuthentication().authenticate(request)
    except Exception:
        return None
    return result[0] if result else None


def user_can_view_layer(user, layer: LayerInfo) -> bool:
    if not user.is_active:
        return False
    if user.is_superuser or layer.owner_id == user.id:
        return True
    return LayerShare.objects.filter(layer=layer, shared_with=user).exists()


# ---------------------------------------------------------------- decision
def authorize_tile_request(request, original_uri: str) -> TileDecision:
    parts = urlsplit(original_uri or "")

    share = SHARE_TILE_RE.match(parts.path)
    if share:
        link, deny = check_share_link(share.group("token"))
        # Log the link's id, never any part of the secret token.
        label = f"link:{str(link.pk)[:8]}" if link else "-"
        if deny:
            return TileDecision(403, deny, token_label=label)
        record_share_link_usage(link)
        return TileDecision(204, layer_table=link.layer.table_name, token_label=label)

    app_tile = APP_TILE_RE.match(parts.path)
    if not app_tile or app_tile.group("source") != settings.MARTIN_LAYER_FUNCTION:
        return TileDecision(403, "malformed")

    table = (parse_qs(parts.query).get("layer") or [""])[0]
    if not LAYER_TABLE_RE.match(table):
        return TileDecision(403, "malformed")

    user = _request_user(request)
    if user is None:
        return TileDecision(401, "login_required")

    layer = LayerInfo.objects.filter(table_name=table).first()
    if layer is None or not user_can_view_layer(user, layer):
        return TileDecision(403, "forbidden", token_label="session")
    return TileDecision(204, layer_table=layer.table_name, token_label="session")


def _shared_secret_ok(request) -> bool:
    expected = getattr(settings, "TILE_AUTH_SHARED_SECRET", "")
    if not expected:
        return bool(settings.DEBUG)  # tolerated only for local DEBUG runs
    return constant_time_compare(request.headers.get("X-Tile-Auth-Secret", ""), expected)


@never_cache
@require_GET
def validate_tile_request(request):
    """Nginx ``auth_request`` target. 204 allow / 401 sign-in required / 403 refused."""
    if not _shared_secret_ok(request):
        logger.warning("Tile auth called without a valid shared secret from %s", request.META.get("REMOTE_ADDR"))
        return HttpResponse(status=403)

    decision = authorize_tile_request(request, request.headers.get("X-Original-URI", ""))
    response = HttpResponse(status=decision.status)
    response["X-Tile-Token-Id"] = decision.token_label
    if decision.layer_table:
        response["X-Tile-Layer"] = decision.layer_table
    if decision.reason:
        response["X-Tile-Deny-Reason"] = decision.reason
    return response
