"""Map URL endpoints (Django fallback when Nginx is not in front).

* ``/m/<token>/style.json`` — Map URL (composition Style Spec). Always Django.
* ``/m/<token>/<table>/<z>/<x>/<y>.pbf`` — tiles for a layer on that map. In
  Docker, Nginx + Martin handle ``.pbf``; this view is the no-Nginx fallback.
"""
from __future__ import annotations

import json

from django.http import HttpResponse
from django.views.decorators.http import require_GET

from apps.layers.share_http import cors, literal_template_uri, proxy_martin_tile, share_deny_response

from .share_auth import (
    check_map_share_link,
    map_share_allows_table,
    record_map_share_link_usage,
)
from .share_style import build_map_share_style


@require_GET
def serve_shared_map_tile(request, token, table, z, x, y):
    link, deny = check_map_share_link(token)
    if deny:
        return share_deny_response(deny)
    if not map_share_allows_table(link, table):
        return cors(HttpResponse("You do not have access to this layer.", status=403, content_type="text/plain"))

    record_map_share_link_usage(link)
    return proxy_martin_tile(table=table, z=z, x=x, y=y)


@require_GET
def serve_shared_map_style(request, token):
    """Public Mapbox Style Spec for a map share token (same auth rules as tiles)."""
    link, deny = check_map_share_link(token)
    if deny:
        return share_deny_response(deny)

    def tiles_url_for_table(table: str) -> str:
        return literal_template_uri(request, f"/m/{link.token}/{table}/{{z}}/{{x}}/{{y}}.pbf")

    doc = build_map_share_style(map_project=link.map, tiles_url_for_table=tiles_url_for_table)
    response = HttpResponse(
        json.dumps(doc, separators=(",", ":")),
        content_type="application/json",
    )
    response["Cache-Control"] = "public, max-age=60"
    return cors(response)
