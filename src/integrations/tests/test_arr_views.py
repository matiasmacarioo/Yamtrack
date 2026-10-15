"""Tests for the Sonarr views."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import (
    TV,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
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


TV_METADATA = {
    "media_id": 1396,
    "media_type": "tv",
    "source": "tmdb",
    "source_url": "https://www.themoviedb.org/tv/1396",
    "title": "Breaking Bad",
    "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
    "synopsis": "A chemistry teacher.",
    "genres": ["Drama"],
    "score": 8.9,
    "score_count": 1000,
    "details": {"format": "TV", "status": "Ended"},
    "related": {},
    "cast": [],
    "tvdb_id": 81189,
    "external_links": {},
    "last_episode_season": 5,
    "next_episode_season": None,
    "providers": [],
}

SEASON_METADATA = {
    **TV_METADATA,
    "media_type": "season",
    "season_number": 2,
    "episodes": [],
    "max_progress": 13,
    "details": {"format": "Season", "status": "Ended"},
}


@override_settings(**SONARR_SETTINGS)
class SonarrTemplateTest(TestCase):
    """Check the Sonarr buttons actually render on the details pages."""

    def setUp(self):
        """Log a user in and fake the provider metadata."""
        credentials = {
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass",
        }
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.force_login(self.user)

    def details_url(self):
        """Return the TV details page URL."""
        return reverse(
            "media_details",
            kwargs={
                "source": "tmdb",
                "media_type": "tv",
                "media_id": "1396",
                "title": "breaking-bad",
            },
        )

    def season_url(self):
        """Return the season details page URL."""
        return reverse(
            "season_details",
            kwargs={
                "source": "tmdb",
                "media_id": "1396",
                "title": "breaking-bad",
                "season_number": 2,
            },
        )

    def render_details(self, url, metadata):
        """Render a details page with the provider metadata stubbed out."""
        with (
            patch(
                "app.views.services.get_media_metadata",
                return_value=metadata,
            ),
            patch("app.views.tmdb.filter_providers", return_value=[]),
            patch("app.views.tmdb.process_episodes", return_value=[]),
        ):
            return self.client.get(url)

    def test_tv_page_shows_the_series_button(self):
        """The TV page offers to add the whole series."""
        response = self.render_details(self.details_url(), TV_METADATA)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Add to Sonarr", content)
        self.assertIn(
            reverse("sonarr_add_tv", kwargs={"source": "tmdb", "media_id": "1396"}),
            content,
        )

    def test_season_page_shows_the_season_button(self):
        """The season page names the season it will monitor."""
        tv_with_seasons = {**SEASON_METADATA, "season/2": SEASON_METADATA}
        response = self.render_details(self.season_url(), tv_with_seasons)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Add to Sonarr", content)
        self.assertIn("S2", content)
        self.assertIn("season/2", content)

    def test_button_is_hidden_when_disabled(self):
        """Without configuration the action is not offered at all."""
        with override_settings(SONARR_ENABLED=False):
            response = self.render_details(self.details_url(), TV_METADATA)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add to Sonarr", response.content.decode())

    def test_button_is_hidden_for_manual_entries(self):
        """Manual shows have no provider id to hand to Sonarr."""
        metadata = {**TV_METADATA, "source": "manual"}
        response = self.render_details(self.details_url(), metadata)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add to Sonarr", response.content.decode())

    def test_search_toggle_reflects_the_env_default(self):
        """The toggle starts checked when SONARR_SEARCH_ON_ADD is True."""
        with override_settings(SONARR_SEARCH_ON_ADD=True):
            response = self.render_details(self.details_url(), TV_METADATA)

        content = response.content.decode()
        self.assertIn('name="search"', content)
        self.assertIn("checked", content)


@override_settings(**SONARR_SETTINGS)
class SonarrHomeGridTest(TestCase):
    """The home grid trades the history button for a Sonarr action on TV."""

    def setUp(self):
        """Log a user in and keep the season auto-creation quiet."""
        credentials = {
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass",
        }
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.force_login(self.user)

        def fake_metadata(media_type, *_args, **_kwargs):
            """Return just enough metadata for the model save hooks."""
            if media_type == MediaTypes.TV.value:
                return {
                    "title": "Breaking Bad",
                    "image": "http://example.com/image.jpg",
                    "details": {"seasons": 2},
                    "related": {"seasons": []},
                    "max_progress": 99,
                }
            return {
                "title": "Test Movie",
                "image": "http://example.com/image.jpg",
                "max_progress": 99,
            }

        metadata_patcher = patch(
            "app.models.providers.services.get_media_metadata",
            side_effect=fake_metadata,
        )
        metadata_patcher.start()
        self.addCleanup(metadata_patcher.stop)

    def track_season(self, media_id, season_number):
        """Track one season of a show, in progress."""
        tv_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="http://example.com/image.jpg",
        )
        tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        season_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Breaking Bad",
            image="http://example.com/image.jpg",
            season_number=season_number,
        )
        Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
        )

    def track_movie(self, media_id):
        """Track a movie, in progress."""
        movie_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

    def home_content(self):
        """Render the home page and return its HTML."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_season_is_offered_to_sonarr_with_search(self):
        """An in-progress season gets the season action, searching on add."""
        self.track_season(media_id="1396", season_number=2)

        content = self.home_content()

        self.assertIn(
            reverse(
                "sonarr_add_tv_season",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_id": "1396",
                    "season_number": 2,
                },
            ),
            content,
        )
        self.assertEqual(content.count('name="search" value="true"'), 1)
        self.assertNotIn("View your activity history", content)

    def test_other_media_types_keep_the_history_button(self):
        """Movies have no Sonarr equivalent, so they keep their history button."""
        self.track_movie(media_id="603")

        content = self.home_content()

        self.assertIn("View your activity history", content)
        self.assertNotIn("/sonarr/add/", content)

    def test_disabled_sonarr_keeps_the_history_button(self):
        """Without Sonarr the TV cards keep their history button."""
        self.track_season(media_id="1396", season_number=2)

        with override_settings(SONARR_ENABLED=False):
            content = self.home_content()

        self.assertIn("View your activity history", content)
        self.assertNotIn("/sonarr/add/", content)
