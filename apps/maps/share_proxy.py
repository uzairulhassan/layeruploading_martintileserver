"""Map URL endpoints (Django fallback when Nginx is not in front).

* ``/m/<token>/style.json`` — Map URL (composition Style Spec). Always Django.
* ``/m/<token>/<table>/<z>/<x>/<y>.pbf`` — tiles for a layer on that map. In
  Docker, Nginx + Martin handle ``.pbf``; this view is the no-Nginx fallback.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from apps.layers.tile_auth import SHARE_DENY_MESSAGE, SHARE_DENY_STATUS

from .share_auth import (
    check_map_share_link,
    map_share_allows_table,
    record_map_share_link_usage,
)
from .share_style import build_map_share_style


def _cors(response):
    response["Access-Control-Allow-Origin"] = "*"
    return response


def _share_deny_response(deny: str) -> HttpResponse:
    return _cors(
        HttpResponse(SHARE_DENY_MESSAGE[deny], status=SHARE_DENY_STATUS[deny], content_type="text/plain")
    )


def _literal_template_uri(request, path: str) -> str:
    """Absolute URI with literal ``{z}/{x}/{y}`` (Django otherwise percent-encodes braces)."""
    url = request.build_absolute_uri(path)
    return (
        url.replace("%7Bz%7D", "{z}")
        .replace("%7Bx%7D", "{x}")
        .replace("%7By%7D", "{y}")
        .replace("%7bz%7d", "{z}")
        .replace("%7bx%7d", "{x}")
        .replace("%7by%7d", "{y}")
    )


def serve_shared_map_tile(request, token, table, z, x, y):
    link, deny = check_map_share_link(token)
    if deny:
        return _share_deny_response(deny)
    if not map_share_allows_table(link, table):
        return _cors(HttpResponse("You do not have access to this layer.", status=403, content_type="text/plain"))

    record_map_share_link_usage(link)
    upstream_url = (
        f"{settings.MARTIN_INTERNAL_URL.rstrip('/')}/{settings.MARTIN_LAYER_FUNCTION}"
        f"/{z}/{x}/{y}?{urlencode({'layer': table})}"
    )

    try:
        req = urllib.request.Request(upstream_url, headers={"Accept": "application/x-protobuf"})
        with urllib.request.urlopen(req, timeout=10) as upstream:
            tile_bytes = upstream.read()
            content_type = upstream.headers.get("Content-Type", "application/x-protobuf")
            upstream_status = upstream.status
    except urllib.error.HTTPError as exc:
        return _cors(HttpResponse("Tile not available.", status=exc.code, content_type="text/plain"))
    except urllib.error.URLError:
        return _cors(HttpResponse("Tile server unreachable.", status=502, content_type="text/plain"))

    response = HttpResponse(tile_bytes, content_type=content_type, status=upstream_status)
    response["Cache-Control"] = "public, max-age=60"
    return _cors(response)


@require_GET
def serve_shared_map_style(request, token):
    """Public Mapbox Style Spec for a map share token (same auth rules as tiles)."""
    link, deny = check_map_share_link(token)
    if deny:
        return _share_deny_response(deny)

    def tiles_url_for_table(table: str) -> str:
        return _literal_template_uri(request, f"/m/{link.token}/{table}/{{z}}/{{x}}/{{y}}.pbf")

    doc = build_map_share_style(map_project=link.map, tiles_url_for_table=tiles_url_for_table)
    response = HttpResponse(
        json.dumps(doc, separators=(",", ":")),
        content_type="application/json",
    )
    response["Cache-Control"] = "public, max-age=60"
    return _cors(response)
