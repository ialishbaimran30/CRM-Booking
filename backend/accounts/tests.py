from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import User


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client.apps.googleusercontent.com")
class GoogleSignInViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/google/"
        self.identity = {
            "email": "person@example.com",
            "subject": "google-subject-123",
            "full_name": "Test Person",
            "picture": "https://example.com/avatar.jpg",
        }

    @patch("accounts.views.verify_google_id_token")
    def test_creates_google_user_and_returns_jwts(self, verify_token):
        verify_token.return_value = self.identity

        response = self.client.post(self.url, {"id_token": "google-id-token"}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.identity["email"])
        user = User.objects.get(email=self.identity["email"])
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.google_subject, self.identity["subject"])

    @patch("accounts.views.verify_google_id_token")
    def test_links_a_matching_password_account(self, verify_token):
        user = User.objects.create_user(
            username="existing-user",
            email=self.identity["email"],
            password="safe-test-password",
        )
        verify_token.return_value = self.identity

        response = self.client.post(self.url, {"id_token": "google-id-token"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        user.refresh_from_db()
        self.assertEqual(user.google_subject, self.identity["subject"])
        self.assertTrue(user.has_usable_password())

    def test_rejects_missing_id_token(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)
