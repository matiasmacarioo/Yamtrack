"""Tests for the API authentication endpoints."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status


class AuthTest(TestCase):
    """Test API key authentication."""

    def setUp(self):
        """Create a test user."""
        self.testpass = "testpass123"
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password=self.testpass,
        )

    def test_unauthenticated_request_fails(self):
        """Test that unauthenticated requests return 401."""
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_key_bearer_authenticates(self):
        """A user's static API token authorizes requests as that user."""
        response = self.client.get(
            "/api/auth/me/", headers={"authorization": f"Bearer {self.user.token}"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")

    def test_api_key_x_header_authenticates(self):
        """The X-API-Key header also authorizes requests."""
        response = self.client.get(
            "/api/auth/me/", headers={"x-api-key": self.user.token}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")

    def test_invalid_api_key_rejected(self):
        """An unknown API key is rejected with 401."""
        response = self.client.get(
            "/api/auth/me/", headers={"authorization": "Bearer not-a-real-key"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_key_resolves_correct_user(self):
        """The API key maps to the owning user, not another account."""
        otherpass = "otherpass123"
        other = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password=otherpass,
        )
        response = self.client.get(
            "/api/auth/me/", headers={"authorization": f"Bearer {self.user.token}"}
        )
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertNotEqual(response.data["email"], other.email)
