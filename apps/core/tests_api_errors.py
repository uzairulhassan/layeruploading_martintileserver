"""Tests for centralized API error handling and request IDs."""
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.api_errors import (
    INTERNAL_ERROR_MESSAGE,
    ErrorCode,
    PublicError,
    error_response,
)
from apps.core.exception_handler import custom_exception_handler
from apps.core.request_id import REQUEST_ID_ATTR, RequestIDMiddleware
from apps.layers.services import (
    LAYER_IMPORT_FAILED_MESSAGE,
    LAYER_IMPORT_TOOLS_UNAVAILABLE_MESSAGE,
    LayerImportError,
    run_ogr2ogr,
)


class RequestIDMiddlewareTests(SimpleTestCase):
    def test_generates_and_echoes_request_id(self):
        factory = RequestFactory()
        request = factory.get("/")

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        response = RequestIDMiddleware(get_response)(request)
        self.assertTrue(getattr(request, REQUEST_ID_ATTR))
        self.assertEqual(response["X-Request-ID"], getattr(request, REQUEST_ID_ATTR))

    def test_accepts_inbound_request_id(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_REQUEST_ID="abc-123")

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        response = RequestIDMiddleware(get_response)(request)
        self.assertEqual(getattr(request, REQUEST_ID_ATTR), "abc-123")
        self.assertEqual(response["X-Request-ID"], "abc-123")


class ExceptionHandlerTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _context(self, request=None):
        request = request or self.factory.get("/api/test/")
        setattr(request, REQUEST_ID_ATTR, "test-req-id")
        return {"request": request, "view": APIView()}

    def test_public_error_returns_safe_contract(self):
        response = custom_exception_handler(
            PublicError("Safe message.", code=ErrorCode.LAYER_IMPORT_FAILED),
            self._context(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], ErrorCode.LAYER_IMPORT_FAILED)
        self.assertEqual(response.data["message"], "Safe message.")
        self.assertEqual(response.data["detail"], "Safe message.")
        self.assertEqual(response.data["request_id"], "test-req-id")
        self.assertIsNone(response.data["errors"])
        self.assertEqual(response["X-Request-ID"], "test-req-id")

    def test_validation_error_includes_field_errors(self):
        response = custom_exception_handler(
            ValidationError({"file": ["This field is required."]}),
            self._context(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], ErrorCode.VALIDATION_ERROR)
        self.assertEqual(response.data["errors"]["file"], ["This field is required."])
        self.assertEqual(response.data["request_id"], "test-req-id")

    def test_unexpected_exception_is_sanitized(self):
        response = custom_exception_handler(
            RuntimeError("SELECT * FROM secrets WHERE path='/etc/passwd'"),
            self._context(),
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], ErrorCode.INTERNAL_ERROR)
        self.assertEqual(response.data["message"], INTERNAL_ERROR_MESSAGE)
        self.assertNotIn("SELECT", response.data["message"])
        self.assertNotIn("passwd", response.data["detail"])
        self.assertEqual(response.data["request_id"], "test-req-id")

    def test_error_response_helper_shape(self):
        request = self.factory.get("/")
        setattr(request, REQUEST_ID_ATTR, "helper-id")
        response = error_response(
            request,
            message="Only the owner can share this map.",
            code=ErrorCode.PERMISSION_DENIED,
            status_code=403,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], ErrorCode.PERMISSION_DENIED)
        self.assertEqual(response.data["message"], "Only the owner can share this map.")
        self.assertEqual(response.data["request_id"], "helper-id")


class Ogr2ogrSanitizationTests(SimpleTestCase):
    @patch("apps.layers.services.subprocess.run")
    def test_ogr2ogr_failure_does_not_leak_stderr(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: password=supersecret host=/var/lib/postgresql",
            stdout="",
        )
        with self.assertRaises(LayerImportError) as ctx:
            run_ogr2ogr(["ogr2ogr", "dummy"])
        self.assertEqual(str(ctx.exception), LAYER_IMPORT_FAILED_MESSAGE)
        self.assertNotIn("supersecret", str(ctx.exception))
        self.assertNotIn("postgresql", str(ctx.exception))
        self.assertEqual(ctx.exception.code, ErrorCode.LAYER_IMPORT_FAILED)

    @patch("apps.layers.services.subprocess.run", side_effect=FileNotFoundError("missing"))
    def test_ogr2ogr_missing_does_not_leak_path(self, _mock_run):
        with self.assertRaises(LayerImportError) as ctx:
            run_ogr2ogr(["ogr2ogr", "dummy"])
        self.assertEqual(str(ctx.exception), LAYER_IMPORT_TOOLS_UNAVAILABLE_MESSAGE)
        self.assertNotIn("/", str(ctx.exception))
        self.assertNotIn("\\", str(ctx.exception))
