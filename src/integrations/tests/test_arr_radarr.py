"""Tests for the Radarr integration."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from integrations.arr import radarr
from integrations.arr.client import ArrError

LOOKUP_RESULT = {
    "title": "The Matrix",
    "tmdbId": 603,
    "imdbId": "tt0133093",
    "year": 1999,
    "minimumAvailability": "released",
}

EXISTING_MOVIE = {
    "id": 7,
    "title": "The Matrix",
    "tmdbId": 603,
    "imdbId": "tt0133093",
    "monitored": True,
}

# The same movie once it is present but unmonitored.
UNMONITORED_MOVIE = {**EXISTING_MOVIE, "monitored": False}

# What Radarr returns right after the movie was added.
CREATED_MOVIE = {
    "id": 42,
    "title": "The Matrix",
    "tmdbId": 603,
    "imdbId": "tt0133093",
    "monitored": True,
}

RADARR_SETTINGS = {
    "RADARR_ENABLED": True,
    "RADARR_URL": "http://radarr.test",
    "RADARR_API_KEY": "k3y",
    "RADARR_QUALITY_PROFILE": "HD - 720p/1080p",
    "RADARR_ROOT_FOLDER": "/movies",
    "RADARR_MINIMUM_AVAILABILITY": "released",
    "RADARR_SEARCH_ON_ADD": False,
}


class FakeClient:
    """Stand in for ArrClient recording the requests it receives."""

    def __init__(self, responses=None):
        """Store a mapping of (method, path) or path to a canned response."""
        self.responses = responses or {}
        self.calls = []

    def _serve(self, method, path, payload):
        self.calls.append((method, path, payload))
        response = self.responses.get((method, path), self.responses.get(path))
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, path, params=None):
        """Record and serve a GET request."""
        return self._serve("GET", path, params)

    def post(self, path, payload=None):
        """Record and serve a POST request."""
        return self._serve("POST", path, payload)

    def put(self, path, payload=None):
        """Record and serve a PUT request."""
        return self._serve("PUT", path, payload)

    def requests_for(self, method, path):
        """Return the payloads of the recorded calls matching method and path."""
        return [call[2] for call in self.calls if call[0] == method and call[1] == path]


def fresh_client(extra=None):
    """Return a fake client with everything a first time add needs."""
    responses = {
        "movie": [],
        ("POST", "movie"): {"id": 42},
        ("GET", "movie/42"): CREATED_MOVIE,
        ("GET", "movie/7"): EXISTING_MOVIE,
        "movie/lookup": [LOOKUP_RESULT],
        "qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}],
        "rootfolder": [{"id": 1, "path": "/movies"}],
        "command": {"id": 1},
    }
    responses.update(extra or {})
    return FakeClient(responses)


@override_settings(**RADARR_SETTINGS)
class RadarrAddMovieTest(TestCase):
    """Test the Radarr service layer."""

    def add_movie(self, fake, **kwargs):
        """Run add_movie against a fake client and return the result."""
        if fake is None:
            return radarr.add_movie(**kwargs)
        with patch.object(radarr, "get_client", return_value=fake):
            return radarr.add_movie(**kwargs)

    def test_disabled_when_not_configured(self):
        """Without a URL and API key the action reports an error."""
        with override_settings(RADARR_ENABLED=False):
            result = self.add_movie(None, tmdb_id=603, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ERROR)
        self.assertIn("not configured", result.message)

    def test_add_movie_payload(self):
        """A first time add configures the profile, root folder and options."""
        fake = fresh_client()
        result = self.add_movie(fake, tmdb_id=603, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ADDED)

        payloads = fake.requests_for("POST", "movie")
        self.assertEqual(len(payloads), 1)

        payload = payloads[0]
        self.assertEqual(payload["qualityProfileId"], 2)
        self.assertEqual(payload["rootFolderPath"], "/movies")
        self.assertEqual(payload["minimumAvailability"], "released")
        self.assertTrue(payload["monitored"])
        self.assertFalse(payload["addOptions"]["searchForMovie"])

    def test_minimum_availability_is_configurable(self):
        """The configured minimum availability is sent to Radarr."""
        fake = fresh_client()
        with override_settings(RADARR_MINIMUM_AVAILABILITY="announced"):
            self.add_movie(fake, tmdb_id=603, title="The Matrix")

        payload = fake.requests_for("POST", "movie")[0]
        self.assertEqual(payload["minimumAvailability"], "announced")

    def test_search_flag_queues_movie_search(self):
        """The search toggle triggers a MoviesSearch command."""
        fake = fresh_client()
        result = self.add_movie(fake, tmdb_id=603, title="The Matrix", search=True)

        commands = fake.requests_for("POST", "command")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["name"], "MoviesSearch")
        self.assertEqual(commands[0]["movieIds"], [42])
        self.assertIn("search was queued", result.message)

    def test_no_search_command_by_default(self):
        """Without the toggle no command is sent to Radarr."""
        fake = fresh_client()
        self.add_movie(fake, tmdb_id=603, title="The Matrix")

        self.assertEqual(fake.requests_for("POST", "command"), [])

    def test_existing_monitored_movie_is_not_added_twice(self):
        """A movie already monitored sends nothing at all."""
        fake = fresh_client({"movie": [EXISTING_MOVIE]})
        result = self.add_movie(fake, tmdb_id=603, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ALREADY)
        self.assertIn("already", result.message)
        self.assertEqual(fake.requests_for("POST", "movie"), [])
        self.assertEqual(fake.requests_for("PUT", "movie/7"), [])

    def test_existing_unmonitored_movie_is_monitored(self):
        """An existing but unmonitored movie is monitored instead of re-added."""
        fake = fresh_client({"movie": [UNMONITORED_MOVIE]})
        result = self.add_movie(fake, tmdb_id=603, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_UPDATED)
        self.assertIn("now monitored", result.message)
        self.assertEqual(fake.requests_for("POST", "movie"), [])

        puts = fake.requests_for("PUT", "movie/7")
        self.assertEqual(len(puts), 1)
        self.assertTrue(puts[0]["monitored"])

    def test_existing_movie_search_queues_command(self):
        """Searching an already present movie only queues the search."""
        fake = fresh_client({"movie": [EXISTING_MOVIE]})
        self.add_movie(fake, tmdb_id=603, title="The Matrix", search=True)

        commands = fake.requests_for("POST", "command")
        self.assertEqual(commands[0]["name"], "MoviesSearch")
        self.assertEqual(commands[0]["movieIds"], [7])

    def test_lookup_by_imdb_when_tmdb_is_missing(self):
        """A movie without a TMDB id can still be found by its IMDb id."""
        fake = fresh_client()
        result = self.add_movie(fake, imdb_id="tt0133093", title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ADDED)
        self.assertEqual(len(fake.requests_for("POST", "movie")), 1)

    def test_unknown_movie_reports_error(self):
        """A lookup miss is reported instead of raising."""
        fake = fresh_client({"movie/lookup": []})
        result = self.add_movie(fake, tmdb_id=1, title="Nope")

        self.assertEqual(result.outcome, radarr.OUTCOME_ERROR)
        self.assertIn("could not find", result.message)

    def test_api_error_is_reported(self):
        """API failures are turned into a user facing message."""
        fake = fresh_client({"movie": ArrError("boom", status_code=500)})
        result = self.add_movie(fake, tmdb_id=603, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ERROR)
        self.assertIn("boom", result.message)

    def test_missing_ids_cannot_be_added(self):
        """Without any external id Radarr cannot find the movie."""
        fake = fresh_client({"movie/lookup": []})
        result = self.add_movie(fake, title="The Matrix")

        self.assertEqual(result.outcome, radarr.OUTCOME_ERROR)


class RadarrConfigTest(TestCase):
    """Test the Radarr configuration resolvers."""

    def test_disabled_when_not_configured(self):
        """The client is None until a URL and API key are set."""
        with override_settings(RADARR_ENABLED=False):
            self.assertIsNone(radarr.get_client())

    def test_client_is_built_from_settings(self):
        """A configured instance returns a client pointed at it."""
        with override_settings(**RADARR_SETTINGS):
            client = radarr.get_client()
        self.assertEqual(client.base_url, "http://radarr.test")

    def test_quality_profile_name_is_resolved(self):
        """A configured profile name resolves to its Radarr id."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}]})
        with override_settings(**RADARR_SETTINGS):
            self.assertEqual(radarr.resolve_quality_profile(fake), 2)

    def test_quality_profile_id_is_resolved(self):
        """A numeric profile is accepted as an id."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD"}]})
        with override_settings(**{**RADARR_SETTINGS, "RADARR_QUALITY_PROFILE": "2"}):
            self.assertEqual(radarr.resolve_quality_profile(fake), 2)

    def test_unknown_quality_profile_lists_available(self):
        """An unknown profile names the available ones."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}]})
        settings = {**RADARR_SETTINGS, "RADARR_QUALITY_PROFILE": "nope"}
        with (
            override_settings(**settings),
            self.assertRaises(ArrError) as ctx,
        ):
            radarr.resolve_quality_profile(fake)
        self.assertIn("HD - 720p/1080p", str(ctx.exception))

    def test_missing_root_folder_falls_back_to_the_first(self):
        """No configured root folder uses the first one Radarr reports."""
        fake = FakeClient({"rootfolder": [{"id": 1, "path": "/movies"}]})
        with override_settings(**{**RADARR_SETTINGS, "RADARR_ROOT_FOLDER": ""}):
            self.assertEqual(radarr.resolve_root_folder(fake), "/movies")

    def test_windows_root_folder_matches_any_slash_style(self):
        """A Windows root folder matches regardless of slash direction."""
        fake = FakeClient({"rootfolder": [{"id": 7, "path": "D:\\Movies"}]})
        settings = {**RADARR_SETTINGS, "RADARR_ROOT_FOLDER": "d:/movies/"}
        with override_settings(**settings):
            self.assertEqual(radarr.resolve_root_folder(fake), "D:\\Movies")

        settings = {**RADARR_SETTINGS, "RADARR_ROOT_FOLDER": "D:\\Movies"}
        with override_settings(**settings):
            self.assertEqual(radarr.resolve_root_folder(fake), "D:\\Movies")

    def test_configured_root_folder_must_exist(self):
        """A configured root folder that Radarr does not know errors out."""
        fake = FakeClient({"rootfolder": [{"id": 1, "path": "/movies"}]})
        settings = {**RADARR_SETTINGS, "RADARR_ROOT_FOLDER": "/nope"}
        with (
            override_settings(**settings),
            self.assertRaises(ArrError),
        ):
            radarr.resolve_root_folder(fake)

    def test_minimum_availability_defaults_to_released(self):
        """An unset minimum availability falls back to released."""
        settings = {**RADARR_SETTINGS, "RADARR_MINIMUM_AVAILABILITY": ""}
        with override_settings(**settings):
            self.assertEqual(radarr.resolve_minimum_availability(), "released")

    def test_minimum_availability_is_configurable(self):
        """A configured minimum availability is returned as is."""
        settings = {**RADARR_SETTINGS, "RADARR_MINIMUM_AVAILABILITY": "announced"}
        with override_settings(**settings):
            self.assertEqual(radarr.resolve_minimum_availability(), "announced")
