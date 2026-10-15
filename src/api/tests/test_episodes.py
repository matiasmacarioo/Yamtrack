"""Tests for the API episode endpoint."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status

from app.models import Episode

SEASON_METADATA = {
    "image": "https://example.com/season1.jpg",
    "episodes": [{"episode_number": 1, "still_path": None}],
}

TV_METADATA = {
    "title": "Test TV Show",
    "image": "https://example.com/tv.jpg",
    "max_progress": 24,
    "season/1": SEASON_METADATA,
    "details": {"seasons": 1},
    "related": {},
}


def get_metadata_side_effect(media_type, *args, **kwargs):  # noqa: ARG001
    """Return different mock data based on media type."""
    if media_type == "tv_with_seasons":
        return TV_METADATA
    if media_type == "tv":
        return TV_METADATA
    if media_type == "season":
        return SEASON_METADATA
    return SEASON_METADATA


class EpisodeApiTest(TestCase):
    """Test episode tracking endpoint."""

    def setUp(self):
        """Create a test user."""
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",  # noqa: S106
        )
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {self.user.token}"

    @patch(
        "app.providers.services.get_media_metadata",
        side_effect=get_metadata_side_effect,
    )
    def test_episode_create(self, _mock_get_metadata):
        """Test creating a watched episode entry."""
        response = self.client.post(
            "/api/episodes/",
            {
                "media_id": "999",
                "source": "tmdb",
                "season_number": 1,
                "episode_number": 1,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch(
        "app.providers.services.get_media_metadata",
        side_effect=get_metadata_side_effect,
    )
    def test_episode_update_end_date(self, _mock_get_metadata):
        """Re-sending the same episode with end_date updates its watch date."""
        payload = {
            "media_id": "999",
            "source": "tmdb",
            "season_number": 1,
            "episode_number": 1,
        }
        self.client.post(
            "/api/episodes/",
            payload,
            content_type="application/json",
        )
        response = self.client.post(
            "/api/episodes/",
            {**payload, "end_date": "2024-01-02T12:30:00Z"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        episode = Episode.objects.get(
            related_season__item__media_id="999",
            item__episode_number=1,
        )
        self.assertEqual(
            episode.end_date.isoformat(),
            "2024-01-02T12:30:00+00:00",
        )
