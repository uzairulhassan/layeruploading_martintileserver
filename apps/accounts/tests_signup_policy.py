from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.signup_policy import PUBLIC_SIGNUP_CLOSED_MESSAGE

User = get_user_model()


class PublicSignupGateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "username": "newbie",
            "email": "newbie@example.com",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        }

    @override_settings(ALLOW_PUBLIC_SIGNUP=False)
    def test_register_api_closed(self):
        response = self.client.post("/api/auth/register/", self.payload, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"], PUBLIC_SIGNUP_CLOSED_MESSAGE)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    @override_settings(ALLOW_PUBLIC_SIGNUP=True)
    def test_register_api_open(self):
        response = self.client.post("/api/auth/register/", self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username="newbie").exists())

    @override_settings(ALLOW_PUBLIC_SIGNUP=False)
    def test_signup_page_closed_has_no_form(self):
        response = self.client.get(reverse("core:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, PUBLIC_SIGNUP_CLOSED_MESSAGE)
        self.assertNotContains(response, 'id="register-form"')
        self.assertNotContains(response, "register_form.js")

    @override_settings(ALLOW_PUBLIC_SIGNUP=True)
    def test_signup_page_open_has_form(self):
        response = self.client.get(reverse("core:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="register-form"')
        self.assertContains(response, "register_form.js")

    @override_settings(ALLOW_PUBLIC_SIGNUP=False)
    def test_onetime_still_allowed_when_public_signup_closed(self):
        self.assertFalse(User.objects.exists())
        response = self.client.post(
            "/api/auth/onetime/",
            {
                "username": "bootstrap",
                "email": "admin@example.com",
                "password": "Secret123!",
                "password_confirm": "Secret123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username="bootstrap", is_superuser=True).exists())
