"""Hardening coverage: POST-only logout, avatar re-encode, share TTL, tile secret."""
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.layers.models import LayerInfo, LayerShareLink
from apps.layers.share_policy import validate_share_expires_at
from apps.layers.tile_auth import validate_tile_request

User = get_user_model()


class LogoutPostOnlyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logout_user",
            email="logout@example.com",
            password="Secret123!",
        )
        self.client = Client()

    def test_get_logout_does_not_clear_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_post_logout_clears_session(self):
        self.client.force_login(self.user)
        response = self.client.post("/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.session.get("_auth_user_id"))


class AvatarSanitizeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="avatar_user",
            email="avatar@example.com",
            password="Secret123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _png_bytes(self):
        buf = BytesIO()
        Image.new("RGB", (64, 64), color=(20, 40, 60)).save(buf, format="PNG")
        return buf.getvalue()

    def test_avatar_upload_is_reencoded(self):
        upload = SimpleUploadedFile("photo.png", self._png_bytes(), content_type="image/png")
        response = self.client.post("/api/auth/me/avatar/", {"avatar": upload}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name)
        self.user.avatar.open("rb")
        with Image.open(self.user.avatar) as img:
            img.verify()

    def test_non_image_bytes_rejected(self):
        upload = SimpleUploadedFile("fake.png", b"not-an-image-payload", content_type="image/png")
        response = self.client.post("/api/auth/me/avatar/", {"avatar": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)


class ShareExpiryPolicyTests(SimpleTestCase):
    @override_settings(SHARE_LINK_MAX_TTL_DAYS=30)
    def test_far_future_expiry_rejected(self):
        with self.assertRaises(serializers.ValidationError):
            validate_share_expires_at(timezone.now() + timedelta(days=60))

    @override_settings(SHARE_LINK_MAX_TTL_DAYS=30)
    def test_null_and_near_future_ok(self):
        self.assertIsNone(validate_share_expires_at(None))
        near = timezone.now() + timedelta(days=7)
        self.assertEqual(validate_share_expires_at(near), near)


@override_settings(TILE_AUTH_SHARED_SECRET="", DEBUG=True, MARTIN_LAYER_FUNCTION="geolayers_tile")
class TileAuthSecretTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            username="tile_owner",
            email="tile@example.com",
            password="Secret123!",
        )
        self.layer = LayerInfo.objects.create(
            name="Tile Layer",
            owner=owner,
            schema_name="layers_data",
            table_name="layer_" + ("a" * 32),
            geometry_type="Polygon",
        )
        self.link = LayerShareLink.objects.create(layer=self.layer, created_by=owner)
        self.factory = RequestFactory()

    def test_debug_allows_empty_secret(self):
        request = self.factory.get(
            "/tiles-auth/validate/",
            HTTP_X_ORIGINAL_URI=f"/x/{self.link.token}/1/1/1.pbf",
        )
        self.assertEqual(validate_tile_request(request).status_code, 204)

    @override_settings(TILE_AUTH_SHARED_SECRET="", DEBUG=False)
    def test_non_debug_rejects_empty_secret_at_request(self):
        request = self.factory.get(
            "/tiles-auth/validate/",
            HTTP_X_ORIGINAL_URI=f"/x/{self.link.token}/1/1/1.pbf",
        )
        self.assertEqual(validate_tile_request(request).status_code, 403)
