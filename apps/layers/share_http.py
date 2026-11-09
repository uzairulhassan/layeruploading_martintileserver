"""Shared HTTP helpers for public Layer/Map URL endpoints (``/x/…``, ``/m/…``)."""
from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse

from .tile_auth import SHARE_DENY_MESSAGE, SHARE_DENY_STATUS


def cors(response: HttpResponse) -> HttpResponse:
    """Share links are token-auth'd with no cookies — wildcard CORS is intentional."""
    response["Access-Control-Allow-Origin"] = "*"
    return response


def share_deny_response(deny: str) -> HttpResponse:
    return cors(
        HttpResponse(SHARE_DENY_MESSAGE[deny], status=SHARE_DENY_STATUS[deny], content_type="text/plain")
    )


def literal_template_uri(request, path: str) -> str:
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


def proxy_martin_tile(*, table: str, z, x, y) -> HttpResponse:
    """Fetch one MVT tile from the internal Martin instance for ``table``."""
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
        return cors(HttpResponse("Tile not available.", status=exc.code, content_type="text/plain"))
    except urllib.error.URLError:
        return cors(HttpResponse("Tile server unreachable.", status=502, content_type="text/plain"))

    response = HttpResponse(tile_bytes, content_type=content_type, status=upstream_status)
    response["Cache-Control"] = "public, max-age=60"
    return cors(response)
