"""Tests for branded HTML error pages and JSON negotiation on unmatched routes."""
import json

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, SimpleTestCase, modify_settings, override_settings

from apps.core.api_errors import INTERNAL_ERROR_MESSAGE, ErrorCode
from apps.core.error_views import page_not_found, permission_denied, server_error

_NO_WHITENOISE = modify_settings(
    MIDDLEWARE={"remove": "whitenoise.middleware.WhiteNoiseMiddleware"}
)


def _anon_request(path="/"):
    request = RequestFactory().get(path)
    request.user = AnonymousUser()
    return request


def _json_body(response):
    return json.loads(response.content.decode("utf-8"))


@_NO_WHITENOISE
@override_settings(DEBUG=False, ROOT_URLCONF="config.urls")
class HtmlErrorPageTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_unknown_path_returns_branded_404_html(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, "GeoTrak Layers", status_code=404)
        self.assertIn("X-Request-ID", response)

    def test_unknown_api_path_returns_json_not_found(self):
        response = self.client.get("/api/this-route-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("application/json", response["Content-Type"])
        payload = _json_body(response)
        self.assertEqual(payload["code"], ErrorCode.NOT_FOUND)
        self.assertEqual(payload["message"], "Not found.")
        self.assertTrue(payload["request_id"])
        self.assertNotIn("<html", response.content.decode("utf-8").lower())

    def test_accept_json_on_unknown_path_returns_json(self):
        response = self.client.get(
            "/missing-browser-path/",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_json_body(response)["code"], ErrorCode.NOT_FOUND)


@_NO_WHITENOISE
@override_settings(DEBUG=True, ROOT_URLCONF="config.urls")
class DebugModeBranded404Tests(SimpleTestCase):
    """DEBUG=True normally shows Django's technical 404; middleware restores branded HTML."""

    def test_unknown_path_still_branded_when_debug(self):
        response = Client().get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, "error-page", status_code=404)


class ErrorViewUnitTests(SimpleTestCase):
    def test_permission_denied_html(self):
        response = permission_denied(_anon_request("/"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access denied", status_code=403)

    def test_permission_denied_json_for_api_path(self):
        response = permission_denied(_anon_request("/api/anything/"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(_json_body(response)["code"], ErrorCode.PERMISSION_DENIED)

    def test_server_error_html_shows_ref_not_exception_text(self):
        response = server_error(_anon_request("/"))
        self.assertEqual(response.status_code, 500)
        body = response.content.decode("utf-8")
        self.assertIn("Something went wrong", body)
        self.assertIn("Ref:", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("SELECT", body)

    def test_server_error_json_is_sanitized(self):
        response = server_error(_anon_request("/api/boom/"))
        self.assertEqual(response.status_code, 500)
        payload = _json_body(response)
        self.assertEqual(payload["code"], ErrorCode.INTERNAL_ERROR)
        self.assertEqual(payload["message"], INTERNAL_ERROR_MESSAGE)

    def test_page_not_found_direct(self):
        response = page_not_found(_anon_request("/gone/"))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
