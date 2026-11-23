"""Stable API error codes, public domain errors, and response helpers.

Client-facing bodies always look like::

    {
      "code": "VALIDATION_ERROR",
      "message": "Please fix the highlighted fields.",
      "detail": "<same as message>",
      "request_id": "...",
      "errors": { ... } | null
    }

Never put exception text, SQL, stack traces, or filesystem paths in ``message``.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.response import Response

from .request_id import get_request_id, set_request_id_header


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    THROTTLED = "THROTTLED"
    BAD_REQUEST = "BAD_REQUEST"
    LAYER_IMPORT_FAILED = "LAYER_IMPORT_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


INTERNAL_ERROR_MESSAGE = "Something went wrong. Please try again."
VALIDATION_ERROR_MESSAGE = "Please fix the highlighted fields."


class PublicError(Exception):
    """Domain error whose ``message`` is safe to show to API clients."""

    default_code = ErrorCode.BAD_REQUEST
    default_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        self.message = str(message)
        self.code = code or self.default_code
        self.status_code = int(status_code or self.default_status)
        super().__init__(self.message)


def stringify_detail(detail) -> str:
    """Flatten DRF ``detail`` (str / list / dict / ErrorDetail) to one public string."""
    if detail is None:
        return ""
    if isinstance(detail, (list, tuple)):
        return " ".join(part for item in detail if (part := stringify_detail(item)))
    if isinstance(detail, dict):
        if "non_field_errors" in detail:
            return stringify_detail(detail["non_field_errors"])
        parts = []
        for key, value in detail.items():
            text = stringify_detail(value)
            if not text:
                continue
            parts.append(text if key in ("non_field_errors", "detail") else f"{key}: {text}")
        return " ".join(parts)
    if isinstance(detail, ErrorDetail):
        return str(detail)
    return str(detail)


def build_error_payload(request, *, code: str, message: str, errors=None) -> dict:
    return {
        "code": code,
        "message": message,
        "detail": message,
        "request_id": get_request_id(request),
        "errors": errors,
    }


def error_response(
    request,
    *,
    message: str,
    code: str = ErrorCode.BAD_REQUEST,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    errors=None,
) -> Response:
    """Standardized error ``Response`` for hand-written view returns."""
    body = build_error_payload(request, code=code, message=message, errors=errors)
    response = Response(body, status=status_code)
    set_request_id_header(response, body["request_id"])
    return response


def code_for_status(status_code: int) -> str:
    if status_code == status.HTTP_400_BAD_REQUEST:
        return ErrorCode.BAD_REQUEST
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return ErrorCode.AUTHENTICATION_FAILED
    if status_code == status.HTTP_403_FORBIDDEN:
        return ErrorCode.PERMISSION_DENIED
    if status_code == status.HTTP_404_NOT_FOUND:
        return ErrorCode.NOT_FOUND
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return ErrorCode.THROTTLED
    if status_code >= 500:
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.BAD_REQUEST
