"""Tests for the Radarr views, buttons and home grid cards."""

import json
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
from integrations.arr import radarr

RADARR_SETTINGS = {
    "RADARR_ENABLED": True,
    "RADARR_URL": "http://radarr.test",
    "RADARR_API_KEY": "k3y",
    "RADARR_QUALITY_PROFILE": "HD",
    "RADARR_ROOT_FOLDER": "/movies",
    "RADARR_MINIMUM_AVAILABILITY": "released",
    "RADARR_SEARCH_ON_ADD": False,
}

METADATA = {
    "media_id": 603,
    "title": "The Matrix",
    "imdb_id": None,
}


@override_settings(**RADARR_SETTINGS)
class RadarrAddMovieViewTest(TestCase):
    """Test the "Add to Radarr" endpoint."""

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
            "radarr_add_movie",
            kwargs={"source": "tmdb", "media_id": "603"},
        )

    def messages_of(self, response):
        """Return the messages of a response as a single searchable string."""
        return " ".join(str(message) for message in get_messages(response.wsgi_request))

    def post(self, url=None, **kwargs):
        """POST to a Radarr endpoint, optionally as an HTMX request."""
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
        with override_settings(RADARR_ENABLED=False):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("not configured", self.messages_of(response))

    def test_manual_source_is_rejected(self):
        """Manual entries have no TMDB id to look up in Radarr."""
        url = reverse("radarr_add_movie", kwargs={"source": "manual", "media_id": "1"})
        response = self.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("Manual entries", self.messages_of(response))

    def test_add_movie_success(self):
        """A successful add shows a success message and redirects back."""
        result = radarr.ArrResult(radarr.OUTCOME_ADDED, "The Matrix was added.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result) as add,
        ):
            response = self.post(data={"next": "/home/"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/home/")
        self.assertIn("was added", self.messages_of(response))

        kwargs = add.call_args.kwargs
        self.assertEqual(kwargs["tmdb_id"], 603)
        self.assertIsNone(kwargs["imdb_id"])
        self.assertFalse(kwargs["search"])

    def test_search_toggle_is_forwarded(self):
        """The search checkbox reaches the service layer as search=True."""
        result = radarr.ArrResult(radarr.OUTCOME_ADDED, "added, a search was queued.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result) as add,
        ):
            self.post(data={"search": "true"})

        self.assertTrue(add.call_args.kwargs["search"])

    def test_already_added_shows_an_info_message(self):
        """An already imported movie is reported as info, not an error."""
        message = "The Matrix is already in Radarr."
        result = radarr.ArrResult(radarr.OUTCOME_ALREADY, message)

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("already", self.messages_of(response))

    def test_service_failure_shows_an_error_message(self):
        """A service error becomes a message instead of a 500."""
        result = radarr.ArrResult(radarr.OUTCOME_ERROR, "Radarr is unreachable.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("unreachable", self.messages_of(response))

    def test_missing_ids_are_rejected(self):
        """A movie without a TMDB or IMDb id cannot be sent to Radarr."""
        metadata = {"media_id": "abc", "title": "Broken", "imdb_id": None}
        url = reverse("radarr_add_movie", kwargs={"source": "tmdb", "media_id": "abc"})

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=metadata,
            ),
            patch("integrations.views.radarr.add_movie") as add,
        ):
            response = self.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("no TMDB or IMDb id", self.messages_of(response))
        add.assert_not_called()

    def test_imdb_id_is_forwarded_when_present(self):
        """A movie looked up by IMDb id passes it to the service layer."""
        metadata = {"media_id": "abc", "title": "The Matrix", "imdb_id": "tt0133093"}
        result = radarr.ArrResult(radarr.OUTCOME_ADDED, "added")
        url = reverse("radarr_add_movie", kwargs={"source": "imdb", "media_id": "abc"})

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=metadata,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result) as add,
        ):
            self.post(url)

        kwargs = add.call_args.kwargs
        self.assertIsNone(kwargs["tmdb_id"])
        self.assertEqual(kwargs["imdb_id"], "tt0133093")

    def test_metadata_failure_is_reported(self):
        """A provider failure is reported instead of raising."""
        with patch(
            "integrations.views.services.get_media_metadata",
            side_effect=ProviderAPIError("TMDB", "timeout"),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 302)
        self.assertIn("Could not load", self.messages_of(response))

    def test_htmx_request_returns_204_with_location(self):
        """HTMX callers get a 204 that tells the shell to soft-navigate."""
        result = radarr.ArrResult(radarr.OUTCOME_ADDED, "The Matrix was added.")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result),
        ):
            response = self.post(
                data={"next": "/home/"},
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 204)
        location = json.loads(response["HX-Location"])
        self.assertEqual(location["path"], "/home/")
        self.assertEqual(location["target"], "#main-content")
        self.assertEqual(location["select"], "#main-content")
        self.assertEqual(location["swap"], "outerHTML show:none")

    def test_htmx_defaults_to_root_when_next_is_missing(self):
        """A missing next value still produces a valid HX-Location path."""
        result = radarr.ArrResult(radarr.OUTCOME_ADDED, "added")

        with (
            patch(
                "integrations.views.services.get_media_metadata",
                return_value=METADATA,
            ),
            patch("integrations.views.radarr.add_movie", return_value=result),
        ):
            response = self.post(HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 204)
        location = json.loads(response["HX-Location"])
        self.assertEqual(location["path"], "/")


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

MOVIE_METADATA = {
    "media_id": 603,
    "media_type": "movie",
    "source": "tmdb",
    "source_url": "https://www.themoviedb.org/movie/603",
    "title": "The Matrix",
    "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
    "synopsis": "A hacker learns the truth.",
    "genres": ["Action"],
    "score": 8.7,
    "score_count": 1000,
    "details": {"format": "Movie", "status": "Released"},
    "related": {},
    "cast": [],
    "external_links": {},
    "providers": [],
}


@override_settings(**RADARR_SETTINGS)
class RadarrTemplateTest(TestCase):
    """Check the Radarr button actually renders on the movie details page."""

    def setUp(self):
        """Log a user in and fake the provider metadata."""
        credentials = {
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass",
        }
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.force_login(self.user)

    def movie_url(self):
        """Return the movie details page URL."""
        return reverse(
            "media_details",
            kwargs={
                "source": "tmdb",
                "media_type": "movie",
                "media_id": "603",
                "title": "the-matrix",
            },
        )

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

    def test_movie_page_shows_the_radarr_button(self):
        """The movie page offers to add the movie."""
        response = self.render_details(self.movie_url(), MOVIE_METADATA)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Add to Radarr", content)
        self.assertIn(
            reverse("radarr_add_movie", kwargs={"source": "tmdb", "media_id": "603"}),
            content,
        )

    def test_movie_page_does_not_show_the_sonarr_button(self):
        """Sonarr cannot take a movie, so its button is not offered."""
        with override_settings(SONARR_ENABLED=True):
            response = self.render_details(self.movie_url(), MOVIE_METADATA)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add to Sonarr", response.content.decode())

    def test_button_is_hidden_when_disabled(self):
        """Without configuration the action is not offered at all."""
        with override_settings(RADARR_ENABLED=False):
            response = self.render_details(self.movie_url(), MOVIE_METADATA)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add to Radarr", response.content.decode())

    def test_button_is_hidden_for_manual_entries(self):
        """Manual movies have no provider id to hand to Radarr."""
        metadata = {**MOVIE_METADATA, "source": "manual"}
        response = self.render_details(self.movie_url(), metadata)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add to Radarr", response.content.decode())

    def test_search_toggle_reflects_the_env_default(self):
        """The toggle starts checked when RADARR_SEARCH_ON_ADD is True."""
        with override_settings(RADARR_SEARCH_ON_ADD=True):
            response = self.render_details(self.movie_url(), MOVIE_METADATA)

        content = response.content.decode()
        self.assertIn('name="search"', content)
        self.assertIn("checked", content)

    def test_tv_page_keeps_the_sonarr_button(self):
        """TV shows keep the Sonarr action and get no Radarr button."""
        with override_settings(SONARR_ENABLED=True):
            response = self.render_details(self.details_url(), TV_METADATA)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Add to Sonarr", content)
        self.assertNotIn("Add to Radarr", content)


@override_settings(**RADARR_SETTINGS)
class RadarrHomeGridTest(TestCase):
    """The home grid trades the history button for a Radarr action on movies."""

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

    def home_content(self):
        """Render the home page and return its HTML."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_movie_is_offered_to_radarr(self):
        """An in-progress movie gets the Radarr action instead of history."""
        self.track_movie(media_id="603")

        content = self.home_content()

        self.assertIn(
            reverse(
                "radarr_add_movie",
                kwargs={"source": Sources.TMDB.value, "media_id": "603"},
            ),
            content,
        )
        self.assertNotIn("View your activity history", content)

    def test_movie_does_not_search_by_default(self):
        """The home card does not ask Radarr to grab anything by default."""
        self.track_movie(media_id="603")

        content = self.home_content()

        self.assertEqual(content.count('name="search" value="true"'), 0)

    def test_movie_searches_when_configured(self):
        """RADARR_SEARCH_ON_ADD makes the home card queue a search."""
        self.track_movie(media_id="603")

        with override_settings(RADARR_SEARCH_ON_ADD=True):
            content = self.home_content()

        self.assertEqual(content.count('name="search" value="true"'), 1)

    def test_tv_keeps_sonarr_and_not_radarr(self):
        """TV seasons keep their Sonarr action and get no Radarr button."""
        with override_settings(SONARR_ENABLED=True):
            self.track_season(media_id="1396", season_number=2)
            content = self.home_content()

        self.assertIn("/sonarr/add/", content)
        self.assertNotIn("/radarr/add/", content)

    def test_disabled_radarr_keeps_the_history_button(self):
        """Without Radarr the movie cards keep their history button."""
        self.track_movie(media_id="603")

        with override_settings(RADARR_ENABLED=False):
            content = self.home_content()

        self.assertIn("View your activity history", content)
        self.assertNotIn("/radarr/add/", content)

    def test_disabled_radarr_renders_the_history_modal(self):
        """The history modal is kept alongside the history button."""
        self.track_movie(media_id="603")

        with override_settings(RADARR_ENABLED=False):
            content = self.home_content()

        self.assertIn("historyOpen", content)
