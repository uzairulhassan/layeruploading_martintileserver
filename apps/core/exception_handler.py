"""DRF exception handler: sanitize unexpected errors, normalize known ones."""
from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .api_errors import (
    INTERNAL_ERROR_MESSAGE,
    VALIDATION_ERROR_MESSAGE,
    ErrorCode,
    PublicError,
    build_error_payload,
    code_for_status,
    stringify_detail,
)
from .request_id import get_request_id, set_request_id_header

logger = logging.getLogger(__name__)


def _validation_errors(detail) -> dict | list | None:
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, list):
        return {"non_field_errors": detail}
    if detail is not None:
        return {"non_field_errors": [detail]}
    return None


def _code_for_exception(exc: Exception, status_code: int) -> str:
    if isinstance(exc, ValidationError):
        return ErrorCode.VALIDATION_ERROR
    if isinstance(exc, ParseError):
        return ErrorCode.PARSE_ERROR
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return ErrorCode.AUTHENTICATION_FAILED
    if isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        return ErrorCode.PERMISSION_DENIED
    if isinstance(exc, (NotFound, Http404)):
        return ErrorCode.NOT_FOUND
    if isinstance(exc, Throttled):
        return ErrorCode.THROTTLED
    if isinstance(exc, APIException):
        default = getattr(exc, "default_code", None)
        if default and default not in ("error", "invalid"):
            return str(default).upper().replace("-", "_").replace(" ", "_")
    return code_for_status(status_code)


def _message_for_exception(code: str, detail) -> str:
    if code == ErrorCode.INTERNAL_ERROR:
        return INTERNAL_ERROR_MESSAGE
    text = stringify_detail(detail)
    if code == ErrorCode.VALIDATION_ERROR:
        return text or VALIDATION_ERROR_MESSAGE
    return text or INTERNAL_ERROR_MESSAGE


def _finalize(request, *, code: str, message: str, status_code: int, errors=None) -> Response:
    body = build_error_payload(request, code=code, message=message, errors=errors)
    response = Response(body, status=status_code)
    set_request_id_header(response, body["request_id"])
    return response


def custom_exception_handler(exc, context):
    """Normalize known API errors; never leak unexpected exception text to clients."""
    request = context.get("request")
    request_id = get_request_id(request)

    if isinstance(exc, PublicError):
        return _finalize(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        status_code = response.status_code
        code = _code_for_exception(exc, status_code)
        detail = getattr(exc, "detail", response.data)
        errors = _validation_errors(detail) if code == ErrorCode.VALIDATION_ERROR else None
        return _finalize(
            request,
            code=code,
            message=_message_for_exception(code, detail),
            status_code=status_code,
            errors=errors,
        )

    logger.error(
        "Unhandled API exception (request_id=%s): %s",
        request_id,
        exc,
        exc_info=exc,
    )
    return _finalize(
        request,
        code=ErrorCode.INTERNAL_ERROR,
        message=INTERNAL_ERROR_MESSAGE,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
