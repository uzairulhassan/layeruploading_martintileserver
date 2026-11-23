"""Request correlation IDs for logs and API error responses."""
from __future__ import annotations

import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_ATTR = "request_id"

_request_id_var: ContextVar[str | None] = ContextVar("geolayers_request_id", default=None)


def new_request_id() -> str:
    return str(uuid.uuid4())


def set_current_request_id(request_id: str | None):
    return _request_id_var.set(request_id)


def reset_current_request_id(token):
    _request_id_var.reset(token)


def get_current_request_id() -> str | None:
    return _request_id_var.get()


def get_request_id(request) -> str:
    """Return the ID attached by middleware, or a fresh one if missing."""
    if request is None:
        return new_request_id()
    existing = getattr(request, REQUEST_ID_ATTR, None)
    if existing:
        return str(existing)
    return new_request_id()


def set_request_id_header(response, request_id: str):
    if response is not None and request_id:
        response[REQUEST_ID_HEADER] = request_id
    return response


class RequestIDMiddleware:
    """Assign a correlation ID to every request and echo it on the response.

    Accepts an inbound ``X-Request-ID`` when it looks like a simple token
    (max 64 chars, ASCII alnum/hyphen) so proxies can propagate one; otherwise
    generates a UUID4.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = (request.META.get("HTTP_X_REQUEST_ID") or "").strip()
        if incoming and len(incoming) <= 64 and incoming.isascii() and incoming.replace("-", "").isalnum():
            request_id = incoming
        else:
            request_id = new_request_id()
        setattr(request, REQUEST_ID_ATTR, request_id)
        token = set_current_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_current_request_id(token)
        return set_request_id_header(response, request_id)
