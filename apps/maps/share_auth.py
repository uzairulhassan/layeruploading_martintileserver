"""Authorize and meter external map share tile requests (``/m/<token>/…``)."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from .models import MapLayer, MapShareLink, MapShareLinkUsage

logger = logging.getLogger(__name__)

# Keep in sync with geo-infra/nginx/templates/geolayers.conf.template
MAP_SHARE_TILE_RE = re.compile(
    r"^/m/(?P<token>[A-Za-z0-9_-]+)/(?P<table>layer_[0-9a-f]{32})/\d+/\d+/\d+\.pbf$"
)
LAST_USED_RESOLUTION = timedelta(seconds=60)


def check_map_share_link(token: str) -> tuple[MapShareLink | None, str]:
    """Return ``(link, "")`` when usable, else ``(None|link, deny_code)``."""
    link = MapShareLink.objects.select_related("map").filter(token=token).first()
    if link is None:
        return None, "not_found"
    if link.is_blocked:
        return link, "blocked"
    if link.is_expired:
        return link, "expired"
    return link, ""


def map_share_allows_table(link: MapShareLink, table: str) -> bool:
    """True when ``table`` is currently attached to the shared map."""
    return MapLayer.objects.filter(map_id=link.map_id, layer__table_name=table).exists()


def record_map_share_link_usage(link: MapShareLink) -> None:
    """One atomic upsert per tile, plus a throttled last_used_at. Never blocks tiles."""
    now = timezone.now()
    table = MapShareLinkUsage._meta.db_table
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {table} (link_id, date, request_count, last_request_at)
                VALUES (%s, %s, 1, %s)
                ON CONFLICT ON CONSTRAINT map_share_link_usage_unique
                DO UPDATE SET request_count = {table}.request_count + 1,
                              last_request_at = EXCLUDED.last_request_at
                """,
                [link.pk, timezone.localdate(now), now],
            )
        if link.last_used_at is None or now - link.last_used_at >= LAST_USED_RESOLUTION:
            MapShareLink.objects.filter(pk=link.pk).update(last_used_at=now)
    except Exception:  # pragma: no cover - logging must not take tiles down
        logger.exception("Could not record usage for map share link %s", link.pk)
