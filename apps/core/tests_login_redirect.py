from django.contrib.auth import REDIRECT_FIELD_NAME, get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.login_redirect import resolve_post_login_path, should_keep_next

User = get_user_model()


class LoginRedirectHelpersTests(SimpleTestCase):
    def test_should_keep_next(self):
        self.assertFalse(should_keep_next(None))
        self.assertFalse(should_keep_next(""))
        self.assertFalse(should_keep_next("/"))
        self.assertFalse(should_keep_next("/?x=1"))
        self.assertFalse(should_keep_next("//evil.example"))
        self.assertFalse(should_keep_next("https://evil.example/"))
        self.assertTrue(should_keep_next("/layers/"))
        self.assertTrue(should_keep_next("/maps/?new=1"))

    def test_resolve_post_login_path(self):
        self.assertEqual(resolve_post_login_path("/"), "/")
        self.assertEqual(resolve_post_login_path("//evil.example"), "/")
        self.assertEqual(resolve_post_login_path("/account/"), "/account/")
        self.assertEqual(resolve_post_login_path("/maps/?new=1"), "/maps/?new=1")


class LoginRedirectFlowTests(TestCase):
    def test_anonymous_home_redirects_to_clean_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:login"))

    def test_anonymous_deep_link_keeps_next(self):
        response = self.client.get("/layers/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{reverse('core:login')}?{REDIRECT_FIELD_NAME}=/layers/",
        )

    def test_login_strips_useless_next(self):
        response = self.client.get(f"/login/?{REDIRECT_FIELD_NAME}=/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:login"))

    def test_login_keeps_meaningful_next(self):
        response = self.client.get(f"/login/?{REDIRECT_FIELD_NAME}=/maps/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-redirect-field="{REDIRECT_FIELD_NAME}"')

    def test_authenticated_login_honors_next(self):
        user = User.objects.create_user(username="alice", password="Secret123!")
        self.client.force_login(user)
        response = self.client.get(f"/login/?{REDIRECT_FIELD_NAME}=/account/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/account/")
