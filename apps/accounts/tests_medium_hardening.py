from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.roles import ensure_user_role
from apps.accounts.serializers import IDENTITY_CONFLICT_MESSAGE

User = get_user_model()


class SessionVsJwtLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="carol",
            email="carol@example.com",
            password="Secret123!",
        )
        self.client = APIClient()

    def test_login_returns_user_without_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "carol", "password": "Secret123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["username"], "carol")
        self.assertNotIn("access", response.data)

    def test_token_endpoint_returns_jwt_pair(self):
        response = self.client.post(
            "/api/auth/token/",
            {"username": "carol@example.com", "password": "Secret123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)


@override_settings(ALLOW_PUBLIC_SIGNUP=True)
class RegisterHardeningTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="TakenUser",
            email="taken@example.com",
            password="Secret123!",
        )
        self.client = APIClient()

    def test_username_case_conflict_is_generic(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "takenuser",
                "email": "other@example.com",
                "password": "Secret123!",
                "password_confirm": "Secret123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(IDENTITY_CONFLICT_MESSAGE, str(response.data))

    def test_email_conflict_is_generic(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "freshuser",
                "email": "TAKEN@example.com",
                "password": "Secret123!",
                "password_confirm": "Secret123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(IDENTITY_CONFLICT_MESSAGE, str(response.data))


class UserDirectoryPrivacyTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(
            username="me",
            email="me@example.com",
            password="Secret123!",
        )
        User.objects.create_user(
            username="other",
            email="secret@example.com",
            password="Secret123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)

    def test_directory_omits_email_and_email_search(self):
        by_name = self.client.get("/api/auth/users/?search=other")
        self.assertEqual(by_name.status_code, 200)
        results = by_name.data["results"] if isinstance(by_name.data, dict) else by_name.data
        self.assertTrue(results)
        self.assertNotIn("email", results[0])

        by_email = self.client.get("/api/auth/users/?search=secret@example.com")
        results_email = by_email.data["results"] if isinstance(by_email.data, dict) else by_email.data
        self.assertEqual(len(results_email), 0)


class RolePermissionBundleTests(TestCase):
    def test_user_role_receives_upload_and_share_perms(self):
        role = ensure_user_role()
        codenames = set(role.permissions.values_list("codename", flat=True))
        self.assertIn("upload_layerinfo", codenames)
        self.assertIn("share_layerinfo", codenames)
        self.assertIn("create_mapproject", codenames)
        self.assertIn("share_mapproject", codenames)
