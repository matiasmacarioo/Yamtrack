"""Tests for the Sonarr views."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from app.providers.services import ProviderAPIError
from integrations.arr import sonarr

SONARR_SETTINGS = {
    "SONARR_ENABLED": True,
    "SONARR_URL": "http://sonarr.test",
    "SONARR_API_KEY": "k3y",
    "SONARR_QUALITY_PROFILE": "HD",
    "SONARR_ROOT_FOLDER": "/tv",
    "SONARR_LANGUAGE_PROFILE": "",
    "SONARR_SEARCH_ON_ADD": False,
}

METADATA = {
    "media_id": 1396,
    "title": "Breaking Bad",
    "tvdb_id": 81189,
}


@override_settings(**SONARR_SETTINGS)
class SonarrAddTvViewTest(TestCase):
    """Test the "Add to Sonarr" endpoints."""

    def setUp(self):
        """Log a user in so the login middleware lets the request through."""
        credentials = {
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass",
        }
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.force_login(self.user)
        self.url = reverse(
            "sonarr_add_tv",
            kwargs={"source": "tmdb", "media_id": "1396"},
        )

    def messages_of(self, response):
        """Return the messages of a response as a single searchable string."""
        return " ".join(str(message) for message in get_messages(response.wsgi_request))

    def post(self, url=None, **kwargs):
        """POST to a Sonarr endpoint, optionally as an HTMX request."""
        return self.client.post(url or self.url, **kwargs)

    def test_requires_login(self):
        """Anonymous visitors are redirected to the login page."""
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_requires_post(self):
        """A GET request is rejected."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_disabled_returns_error_message(self):
        """Without configuration the action reports a message, not a 500."""
        with override_settings(SONARR_ENABLED=False):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("not configured", self.messages_of(response))

    def test_manual_source_is_rejected(self):
        """Manual entries have no TMDB/TVDB id to look up in Sonarr."""
        url = reverse("sonarr_add_tv", kwargs={"source": "manual", "media_id": "1"})
        response = self.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("Manual entries", self.messages_of(response))

    def test_add_series_success(self):
        """A successful add shows a success message and redirects back."""
        result = sonarr.ArrResult(sonarr.OUTCOME_ADDED, "Breaking Bad was added.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result) as add,
        ):
            response = self.post(data={"next": "/home/"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/home/")
        self.assertIn("was added", self.messages_of(response))

        kwargs = add.call_args.kwargs
        self.assertEqual(kwargs["tvdb_id"], 81189)
        self.assertEqual(kwargs["tmdb_id"], 1396)
        self.assertIsNone(kwargs["season_number"])
        self.assertFalse(kwargs["search"])

    def test_search_toggle_is_forwarded(self):
        """The search checkbox reaches the service layer as search=True."""
        result = sonarr.ArrResult(sonarr.OUTCOME_ADDED, "added, a search was queued.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result) as add,
        ):
            self.post(data={"search": "true"})

        self.assertTrue(add.call_args.kwargs["search"])

    def test_season_endpoint_forwards_the_season_number(self):
        """The season URL monitors only that season."""
        result = sonarr.ArrResult(sonarr.OUTCOME_UPDATED, "season 2 is now monitored.")
        url = reverse(
            "sonarr_add_tv_season",
            kwargs={"source": "tmdb", "media_id": "1396", "season_number": 2},
        )

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result) as add,
        ):
            response = self.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(add.call_args.kwargs["season_number"], 2)
        self.assertIn("season 2", self.messages_of(response))

    def test_already_added_shows_an_info_message(self):
        """An already imported show is reported as info, not an error."""
        message = "Breaking Bad is already in Sonarr."
        result = sonarr.ArrResult(sonarr.OUTCOME_ALREADY, message)

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("already", self.messages_of(response))

    def test_service_failure_shows_an_error_message(self):
        """A service error becomes a message instead of a 500."""
        result = sonarr.ArrResult(sonarr.OUTCOME_ERROR, "Sonarr is unreachable.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("unreachable", self.messages_of(response))

    def test_missing_ids_are_rejected(self):
        """A show without TMDB or TVDB id cannot be sent to Sonarr."""
        metadata = {"media_id": "manual-1", "title": "Broken", "tvdb_id": None}
        url = reverse(
            "sonarr_add_tv",
            kwargs={"source": "tvdb", "media_id": "manual-1"},
        )

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=metadata,
            ),
            patch("integrations.views.sonarr.add_tv") as add,
        ):
            response = self.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("no TMDB or TVDB id", self.messages_of(response))
        add.assert_not_called()

    def test_metadata_failure_is_reported(self):
        """A provider failure is reported instead of raising."""
        with patch(
            "integrations.views.services.get_media_metadata",
            side_effect=ProviderAPIError("TMDB", "timeout"),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("Could not load", self.messages_of(response))

    def test_htmx_request_returns_204_with_redirect(self):
        """HTMX callers get a 204 that tells the browser to reload."""
        result = sonarr.ArrResult(sonarr.OUTCOME_ADDED, "Breaking Bad was added.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result),
        ):
            response = self.post(
                data={"next": "/home/"},
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/home/")

    def test_htmx_defaults_to_root_when_next_is_missing(self):
        """A missing next value still produces a valid HX-Redirect."""
        result = sonarr.ArrResult(sonarr.OUTCOME_ADDED, "added")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result),
        ):
            response = self.post(HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/")

    def test_non_tmdb_source_does_not_pass_a_tmdb_id(self):
        """Only the TMDB source can offer a TMDB id to Sonarr."""
        metadata = {"media_id": "abc", "title": "TVDB only", "tvdb_id": 81189}
        result = sonarr.ArrResult(sonarr.OUTCOME_ADDED, "added")
        url = reverse("sonarr_add_tv", kwargs={"source": "tvdb", "media_id": "81189"})

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=metadata,
            ),
            patch("integrations.views.sonarr.add_tv", return_value=result) as add,
        ):
            self.post(url)

        kwargs = add.call_args.kwargs
        self.assertIsNone(kwargs["tmdb_id"])
        self.assertEqual(kwargs["tvdb_id"], 81189)
