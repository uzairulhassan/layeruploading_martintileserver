"""Branded HTML error pages for browsers; JSON for /api/ (and JSON Accept).

Complements the DRF exception handler — does not replace it. Tile/Nginx deny
bodies stay plain text and are out of scope here.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token

from .api_errors import INTERNAL_ERROR_MESSAGE, ErrorCode, build_error_payload
from .request_id import REQUEST_ID_ATTR, new_request_id, set_request_id_header


def _wants_json(request) -> bool:
    path = (getattr(request, "path", "") or "").lower()
    if path.startswith("/api/"):
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    if not accept or accept.startswith("*/*"):
        return False
    json_pos = accept.find("application/json")
    if json_pos < 0 and "+json" in accept:
        json_pos = accept.find("+json")
    html_pos = accept.find("text/html")
    return json_pos >= 0 and (html_pos < 0 or json_pos < html_pos)


def _ensure_request_id(request) -> str:
    """Return a correlation ID, attaching one to the request when missing.

    ``handler500`` can run with a partially processed request, so middleware
    may not have set an ID yet.
    """
    if request is None:
        return new_request_id()
    existing = getattr(request, REQUEST_ID_ATTR, None)
    if existing:
        return str(existing)
    request_id = new_request_id()
    setattr(request, REQUEST_ID_ATTR, request_id)
    return request_id


def _json_error(request, *, code: str, message: str, status_code: int) -> JsonResponse:
    _ensure_request_id(request)
    body = build_error_payload(request, code=code, message=message, errors=None)
    response = JsonResponse(body, status=status_code)
    set_request_id_header(response, body["request_id"])
    return response


def _html_error(
    request,
    template_name: str,
    *,
    status_code: int,
    show_request_id: bool = False,
) -> HttpResponse:
    request_id = _ensure_request_id(request)
    response = render(
        request,
        template_name,
        {
            "status_code": status_code,
            "request_id": request_id,
            "show_request_id": show_request_id,
        },
        status=status_code,
    )
    set_request_id_header(response, request_id)
    return response


def page_not_found(request, exception=None):
    """Django ``handler404``."""
    if _wants_json(request):
        return _json_error(
            request,
            code=ErrorCode.NOT_FOUND,
            message="Not found.",
            status_code=404,
        )
    return _html_error(request, "errors/404.html", status_code=404)


def permission_denied(request, exception=None):
    """Django ``handler403``."""
    if _wants_json(request):
        return _json_error(
            request,
            code=ErrorCode.PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
            status_code=403,
        )
    return _html_error(request, "errors/403.html", status_code=403)


@requires_csrf_token
def server_error(request):
    """Django ``handler500`` — never expose exception text to the client."""
    if _wants_json(request):
        return _json_error(
            request,
            code=ErrorCode.INTERNAL_ERROR,
            message=INTERNAL_ERROR_MESSAGE,
            status_code=500,
        )
    return _html_error(
        request,
        "errors/500.html",
        status_code=500,
        show_request_id=True,
    )


class BrandedHttpErrorMiddleware:
    """When DEBUG=True, replace Django's technical 404/403 HTML with branded pages.

    JSON responses and the DEBUG 500 yellow page are left alone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not settings.DEBUG:
            return response
        if response.status_code not in (404, 403):
            return response
        if "text/html" not in response.get("Content-Type", ""):
            return response
        peek = response.content[:800] if response.content else b""
        if b"error-page" in peek:
            return response
        if response.status_code == 404:
            return page_not_found(request)
        return permission_denied(request)
