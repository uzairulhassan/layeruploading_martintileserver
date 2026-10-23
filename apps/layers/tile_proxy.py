"""Layer URL endpoints (Django fallback when Nginx is not in front).

* ``/x/<token>/style.json`` — Layer URL (Style Spec). Always served by Django.
* ``/x/<token>/<z>/<x>/<y>.pbf`` — tiles for the same token. In Docker, Nginx
  auth_request + Martin handle ``.pbf``; this view is the no-Nginx fallback.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from .share_style import build_share_style
from .tile_auth import SHARE_DENY_MESSAGE, SHARE_DENY_STATUS, check_share_link, record_share_link_usage


def _cors(response):
    """This endpoint is meant to be fetched from any origin — external sites and
    tools are the point of an external share link, and there's no cookie/session data
    involved (the token in the URL is the only credential), so a wildcard is safe."""
    response["Access-Control-Allow-Origin"] = "*"
    return response


def _share_deny_response(deny: str) -> HttpResponse:
    return _cors(
        HttpResponse(SHARE_DENY_MESSAGE[deny], status=SHARE_DENY_STATUS[deny], content_type="text/plain")
    )


def serve_shared_tile(request, token, z, x, y):
    link, deny = check_share_link(token)
    if deny:
        return _share_deny_response(deny)

    record_share_link_usage(link)
    upstream_url = (
        f"{settings.MARTIN_INTERNAL_URL.rstrip('/')}/{settings.MARTIN_LAYER_FUNCTION}"
        f"/{z}/{x}/{y}?{urlencode({'layer': link.layer.table_name})}"
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
def serve_shared_style(request, token):
    """Public Mapbox Style Spec for a share token (same auth rules as tiles)."""
    link, deny = check_share_link(token)
    if deny:
        return _share_deny_response(deny)

    tiles_url = request.build_absolute_uri(f"/x/{link.token}/{{z}}/{{x}}/{{y}}.pbf")
    # Django percent-encodes ``{`` / ``}`` in build_absolute_uri; MapLibre needs literal braces.
    tiles_url = tiles_url.replace("%7Bz%7D", "{z}").replace("%7Bx%7D", "{x}").replace("%7By%7D", "{y}")
    tiles_url = tiles_url.replace("%7bz%7d", "{z}").replace("%7bx%7d", "{x}").replace("%7by%7d", "{y}")

    doc = build_share_style(layer=link.layer, tiles_url=tiles_url)
    response = HttpResponse(
        json.dumps(doc, separators=(",", ":")),
        content_type="application/json",
    )
    # Short TTL so style edits in GeoLayers show up for external clients quickly.
    response["Cache-Control"] = "public, max-age=60"
    return _cors(response)
