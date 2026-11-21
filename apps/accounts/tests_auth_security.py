from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

User = get_user_model()


@override_settings(
    AUTH_LOGIN_LOCKOUT_ATTEMPTS=3,
    AUTH_LOGIN_LOCKOUT_SECONDS=60,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "auth-security-tests",
        }
    },
)
class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="Secret123!",
        )
        self.client = APIClient()

    def test_lockout_after_repeated_failures(self):
        for _ in range(3):
            response = self.client.post(
                "/api/auth/login/",
                {"username": "alice", "password": "wrong-password"},
                format="json",
            )
            self.assertIn(response.status_code, (401, 400))

        locked = self.client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "Secret123!"},
            format="json",
        )
        self.assertEqual(locked.status_code, 429)

    def test_successful_login_clears_failures_and_sets_session(self):
        # One failure, then success should clear the counter.
        self.client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "wrong-password"},
            format="json",
        )
        response = self.client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "Secret123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("user", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        # Session cookie established for the browser UI.
        self.assertTrue(self.client.session.get("_auth_user_id"))


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "auth-blacklist-tests",
        }
    },
)
class PasswordChangeBlacklistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="Secret123!",
        )
        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        OutstandingToken.objects.create(
            user=self.user,
            jti=refresh.get("jti"),
            token=str(refresh),
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_authenticate(user=self.user)

    def test_password_change_blacklists_outstanding_refresh(self):
        response = self.client.post(
            "/api/auth/me/password/",
            {
                "current_password": "Secret123!",
                "new_password": "NewSecret123!",
                "new_password_confirm": "NewSecret123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        for token in OutstandingToken.objects.filter(user=self.user):
            self.assertTrue(BlacklistedToken.objects.filter(token=token).exists())
