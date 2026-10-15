"""Tests for the API media endpoints."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status

from app.models import Item, MediaTypes, Movie, Sources, Status
from app.providers.services import ProviderAPIError

MOCK_METADATA = {
    "title": "Test Movie",
    "image": "https://example.com/poster.jpg",
    "max_progress": 1,
    "related": {},
}


class MediaApiTest(TestCase):
    """Test media CRUD and home endpoints."""

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def setUp(self, _mock_get_metadata):
        """Create a test user and a test movie."""
        self.testpass = "testpass123"
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password=self.testpass,
        )
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {self.user.token}"

        self.item = Item.objects.create(
            media_id="123",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="https://example.com/poster.jpg",
        )
        self.movie = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
            score=8.0,
            progress=1,
        )

    def test_list_media(self):
        """Test listing media returns only the user's items."""
        response = self.client.get("/api/media/movie/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)

    def test_list_media_other_user(self):
        """Test that other user's media is not included in results."""
        other_user = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password=self.testpass,
        )
        other_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Other Movie",
            image="https://example.com/other.jpg",
        )
        Movie.objects.create(
            item=other_item,
            user=other_user,
            status=Status.PLANNING.value,
        )
        response = self.client.get("/api/media/movie/")
        self.assertEqual(response.data["count"], 1)

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_create_media(self, _mock_get_metadata):
        """Test creating a new media entry from external metadata."""
        response = self.client.post(
            "/api/media/movie/create/",
            {
                "media_id": "789",
                "source": "tmdb",
                "media_type": "movie",
                "status": "Completed",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["item"]["title"], "Test Movie")

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_create_media_with_dates(self, _mock_get_metadata):
        """Custom start_date and end_date must be saved on create."""
        response = self.client.post(
            "/api/media/movie/create/",
            {
                "media_id": "789",
                "source": "tmdb",
                "media_type": "movie",
                "status": "Completed",
                "start_date": "2024-01-01T10:00:00Z",
                "end_date": "2024-01-02T12:30:00Z",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        movie = Movie.objects.get(item__media_id="789")
        self.assertEqual(
            movie.start_date.isoformat(),
            "2024-01-01T10:00:00+00:00",
        )
        self.assertEqual(
            movie.end_date.isoformat(),
            "2024-01-02T12:30:00+00:00",
        )

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_create_duplicate_tv_media(self, _mock_get_metadata):
        """Creating an already tracked TV must return 409, not a 500."""
        payload = {
            "media_id": "456",
            "source": "tmdb",
            "media_type": "tv",
            "status": "Planning",
        }
        self.client.post(
            "/api/media/tv/create/",
            payload,
            content_type="application/json",
        )
        response = self.client.post(
            "/api/media/tv/create/",
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("error", response.data)

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_create_tv_media(self, _mock_get_metadata):
        """TV progress is a read-only property; creating TV must not set it."""
        response = self.client.post(
            "/api/media/tv/create/",
            {
                "media_id": "456",
                "source": "tmdb",
                "media_type": "tv",
                "status": "Planning",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["item"]["title"], "Test Movie")

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_update_tv_progress(self, _mock_get_metadata):
        """PATCHing progress on TV must not 500 on the read-only property."""
        create = self.client.post(
            "/api/media/tv/create/",
            {
                "media_id": "456",
                "source": "tmdb",
                "media_type": "tv",
                "status": "Planning",
            },
            content_type="application/json",
        )
        tv_id = create.data["id"]
        response = self.client.patch(
            f"/api/media/tv/{tv_id}/",
            {"progress": 5},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_update_tv_progress_increase(self, _mock_get_metadata):
        """Increasing TV progress must not 500 on the read-only property."""
        create = self.client.post(
            "/api/media/tv/create/",
            {
                "media_id": "456",
                "source": "tmdb",
                "media_type": "tv",
                "status": "Planning",
            },
            content_type="application/json",
        )
        tv_id = create.data["id"]
        response = self.client.post(
            f"/api/media/tv/{tv_id}/progress/",
            {"operation": "increase"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch(
        "app.providers.services.get_media_metadata",
        side_effect=ProviderAPIError(Sources.TMDB.value, "not found"),
    )
    def test_create_media_metadata_not_found(self, _mock_get_metadata):
        """A provider failure must return 404 JSON, not a 500 HTML page."""
        response = self.client.post(
            "/api/media/movie/create/",
            {
                "media_id": "789",
                "source": "tmdb",
                "media_type": "movie",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_update_media_score(self):
        """Test updating the score of a media item."""
        response = self.client.patch(
            f"/api/media/movie/{self.movie.id}/score/",
            {"score": 9.0},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.score, 9.0)

    def test_increase_progress(self):
        """Test increasing progress on a media item."""
        response = self.client.post(
            f"/api/media/movie/{self.movie.id}/progress/",
            {"operation": "increase"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_media(self):
        """Test deleting a media tracking entry."""
        response = self.client.delete(
            f"/api/media/movie/{self.movie.id}/delete/",
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Movie.objects.filter(id=self.movie.id).exists())

    def test_home_endpoint(self):
        """Test the home endpoint returns in_progress and planning sections."""
        response = self.client.get("/api/home/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("in_progress", response.data)
        self.assertIn("planning", response.data)

    def test_media_delete_unauthenticated(self):
        """Test that unauthenticated users cannot delete media."""
        self.client.defaults.pop("HTTP_AUTHORIZATION", None)
        response = self.client.delete(
            f"/api/media/movie/{self.movie.id}/delete/",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_media(self):
        """Test updating a media entry's fields."""
        response = self.client.patch(
            f"/api/media/movie/{self.movie.id}/",
            {"status": "Planning", "notes": "Updated notes"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.status, "Planning")
        self.assertEqual(self.movie.notes, "Updated notes")

    def test_decrease_progress(self):
        """Test decreasing progress on a media item."""
        response = self.client.post(
            f"/api/media/movie/{self.movie.id}/progress/",
            {"operation": "decrease"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.progress, 0)

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_sync_metadata(self, _mock_get_metadata):
        """Test syncing metadata from the external source."""
        response = self.client.post(
            "/api/sync/tmdb/movie/123/",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("synced", response.data["message"])

    def test_manual_create_get(self):
        """Test GET returns available media types."""
        response = self.client.get("/api/media/manual/create/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("media_types", response.data)

    @patch("app.providers.services.get_media_metadata", return_value=MOCK_METADATA)
    def test_manual_create_movie(self, _mock_get_metadata):
        """Test creating a manual movie entry."""
        response = self.client.post(
            "/api/media/manual/create/",
            {
                "media_type": "movie",
                "title": "My Manual Movie",
                "status": "Completed",
                "progress": 1,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_media_update_unauthenticated(self):
        """Test that unauthenticated users cannot update media."""
        self.client.defaults.pop("HTTP_AUTHORIZATION", None)
        response = self.client.patch(
            f"/api/media/movie/{self.movie.id}/",
            {"notes": "hacked"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
