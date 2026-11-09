"""Layer URL endpoints (Django fallback when Nginx is not in front).

* ``/x/<token>/style.json`` — Layer URL (Style Spec). Always served by Django.
* ``/x/<token>/<z>/<x>/<y>.pbf`` — tiles for the same token. In Docker, Nginx
  auth_request + Martin handle ``.pbf``; this view is the no-Nginx fallback.
"""
import json

from django.http import HttpResponse
from django.views.decorators.http import require_GET

from .share_http import cors, literal_template_uri, proxy_martin_tile, share_deny_response
from .share_style import build_share_style
from .tile_auth import check_share_link, record_share_link_usage


@require_GET
def serve_shared_tile(request, token, z, x, y):
    link, deny = check_share_link(token)
    if deny:
        return share_deny_response(deny)

    record_share_link_usage(link)
    return proxy_martin_tile(table=link.layer.table_name, z=z, x=x, y=y)


@require_GET
def serve_shared_style(request, token):
    """Public Mapbox Style Spec for a share token (same auth rules as tiles)."""
    link, deny = check_share_link(token)
    if deny:
        return share_deny_response(deny)

    tiles_url = literal_template_uri(request, f"/x/{link.token}/{{z}}/{{x}}/{{y}}.pbf")
    doc = build_share_style(layer=link.layer, tiles_url=tiles_url)
    response = HttpResponse(
        json.dumps(doc, separators=(",", ":")),
        content_type="application/json",
    )
    # Short TTL so style edits in GeoLayers show up for external clients quickly.
    response["Cache-Control"] = "public, max-age=60"
    return cors(response)
