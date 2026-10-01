"""Django fallback for share-link tiles: ``/x/<token>/<z>/<x>/<y>.pbf``.

In Docker, Nginx (geo-infra) serves this path itself: it validates the token via
``tile_auth.validate_tile_request`` and proxies straight to Martin, so this view
never runs. It stays for running the app without Nginx (``manage.py runserver``),
and uses the same checks and usage logging.
"""
import urllib.error
import urllib.request
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse

from .tile_auth import SHARE_DENY_MESSAGE, SHARE_DENY_STATUS, check_share_link, record_share_link_usage


def _cors(response):
    """This endpoint is meant to be fetched from any origin — external sites and
    tools are the point of an XYZ share link, and there's no cookie/session data
    involved (the token in the URL is the only credential), so a wildcard is safe."""
    response["Access-Control-Allow-Origin"] = "*"
    return response


def serve_shared_tile(request, token, z, x, y):
    link, deny = check_share_link(token)
    if deny:
        return _cors(HttpResponse(SHARE_DENY_MESSAGE[deny], status=SHARE_DENY_STATUS[deny], content_type="text/plain"))

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
