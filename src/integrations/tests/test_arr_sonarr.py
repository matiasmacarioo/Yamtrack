"""Tests for the Sonarr integration."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from integrations.arr import sonarr
from integrations.arr.client import ArrError

LOOKUP_RESULT = {
    "title": "Breaking Bad",
    "tvdbId": 81189,
    "tmdbId": 1396,
    "year": 2008,
    "seasons": [
        {"seasonNumber": 0, "monitored": False},
        {"seasonNumber": 1, "monitored": False},
        {"seasonNumber": 2, "monitored": False},
    ],
}

EXISTING_SERIES = {
    "id": 7,
    "title": "Breaking Bad",
    "tvdbId": 81189,
    "tmdbId": 1396,
    "seasons": [
        {"seasonNumber": 1, "monitored": True},
        {"seasonNumber": 2, "monitored": False},
    ],
}

SONARR_SETTINGS = {
    "SONARR_ENABLED": True,
    "SONARR_URL": "http://sonarr.test",
    "SONARR_API_KEY": "k3y",
    "SONARR_QUALITY_PROFILE": "HD - 720p/1080p",
    "SONARR_ROOT_FOLDER": "/tv",
    "SONARR_LANGUAGE_PROFILE": "",
    "SONARR_SEARCH_ON_ADD": False,
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
        "series": [],
        ("POST", "series"): {"id": 42},
        "series/lookup": [LOOKUP_RESULT],
        "qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}],
        "rootfolder": [{"id": 1, "path": "/tv"}],
        "languageprofile": [],
        "system/status": {"version": "4.0.5.1234"},
        "command": {"id": 1},
    }
    responses.update(extra or {})
    return FakeClient(responses)


@override_settings(**SONARR_SETTINGS)
class SonarrAddTvTest(TestCase):
    """Test the Sonarr service layer."""

    def setUp(self):
        """Drop cached Sonarr status between tests."""
        cache.clear()

    def add_tv(self, fake, **kwargs):
        """Run add_tv against a fake client and return the result."""
        if fake is None:
            return sonarr.add_tv(**kwargs)
        with patch.object(sonarr, "get_client", return_value=fake):
            return sonarr.add_tv(**kwargs)

    def test_disabled_when_not_configured(self):
        """Without a URL and API key the action reports an error."""
        with override_settings(SONARR_ENABLED=False):
            result = self.add_tv(None, tvdb_id=81189, tmdb_id=1396, title="BB")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ERROR)
        self.assertIn("not configured", result.message)

    def test_add_series_all_seasons_monitored(self):
        """A whole series is added with every season monitored."""
        fake = fresh_client()
        result = self.add_tv(fake, tvdb_id=81189, tmdb_id=1396, title="Breaking Bad")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ADDED)

        payloads = fake.requests_for("POST", "series")
        self.assertEqual(len(payloads), 1)

        payload = payloads[0]
        self.assertEqual(payload["qualityProfileId"], 2)
        self.assertEqual(payload["rootFolderPath"], "/tv")
        self.assertEqual(payload["addOptions"]["monitor"], "all")
        self.assertFalse(payload["addOptions"]["searchForMissingEpisodes"])
        self.assertTrue(all(season["monitored"] for season in payload["seasons"]))

    def test_add_single_season_only_monitors_that_season(self):
        """The season action adds the show with only that season monitored."""
        fake = fresh_client()
        result = self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="Breaking Bad",
            season_number=2,
        )

        self.assertEqual(result.outcome, sonarr.OUTCOME_ADDED)
        self.assertIn("season 2", result.message)

        payload = fake.requests_for("POST", "series")[0]
        self.assertEqual(payload["addOptions"]["monitor"], "none")
        monitored = [s["seasonNumber"] for s in payload["seasons"] if s["monitored"]]
        self.assertEqual(monitored, [2])

    def test_search_flag_queues_series_search(self):
        """The search toggle triggers a SeriesSearch command."""
        fake = fresh_client()
        result = self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="BB",
            search=True,
        )

        commands = fake.requests_for("POST", "command")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["name"], "SeriesSearch")
        self.assertIn("search was queued", result.message)

    def test_search_flag_queues_season_search(self):
        """The search toggle queues a SeasonSearch for a single season."""
        fake = fresh_client()
        self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="BB",
            season_number=2,
            search=True,
        )

        commands = fake.requests_for("POST", "command")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["name"], "SeasonSearch")
        self.assertEqual(commands[0]["seasonNumber"], 2)

    def test_no_search_command_by_default(self):
        """Without the toggle no command is sent to Sonarr."""
        fake = fresh_client()
        self.add_tv(fake, tvdb_id=81189, tmdb_id=1396, title="BB")

        self.assertEqual(fake.requests_for("POST", "command"), [])

    def test_existing_series_is_not_added_twice(self):
        """An already imported show reports 'already' and sends nothing."""
        fake = fresh_client({"series": [EXISTING_SERIES]})
        result = self.add_tv(fake, tvdb_id=81189, tmdb_id=1396, title="Breaking Bad")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ALREADY)
        self.assertIn("already", result.message)
        self.assertEqual(fake.requests_for("POST", "series"), [])

    def test_existing_series_season_is_monitored(self):
        """Monitoring a missing season of an existing show issues a PUT."""
        fake = fresh_client({"series": [EXISTING_SERIES]})
        result = self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="Breaking Bad",
            season_number=2,
        )

        self.assertEqual(result.outcome, sonarr.OUTCOME_UPDATED)

        puts = fake.requests_for("PUT", "series/7")
        self.assertEqual(len(puts), 1)
        monitored = [s["seasonNumber"] for s in puts[0]["seasons"] if s["monitored"]]
        self.assertEqual(monitored, [1, 2])

    def test_existing_monitored_season_is_a_no_op(self):
        """Monitoring an already monitored season does not call the API."""
        fake = fresh_client({"series": [EXISTING_SERIES]})
        result = self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="Breaking Bad",
            season_number=1,
        )

        self.assertEqual(result.outcome, sonarr.OUTCOME_ALREADY)
        self.assertEqual(fake.requests_for("PUT", "series/7"), [])

    def test_existing_series_season_search_only_for_that_season(self):
        """Searching from a season page only searches that season."""
        fake = fresh_client({"series": [EXISTING_SERIES]})
        self.add_tv(
            fake,
            tvdb_id=81189,
            tmdb_id=1396,
            title="Breaking Bad",
            season_number=2,
            search=True,
        )

        commands = fake.requests_for("POST", "command")
        self.assertEqual(commands[0]["name"], "SeasonSearch")
        self.assertEqual(commands[0]["seasonNumber"], 2)

    def test_existing_series_search_covers_the_whole_show(self):
        """Searching from the show page searches every episode."""
        fake = fresh_client({"series": [EXISTING_SERIES]})
        self.add_tv(fake, tvdb_id=81189, tmdb_id=1396, title="BB", search=True)

        commands = fake.requests_for("POST", "command")
        self.assertEqual(commands[0]["name"], "SeriesSearch")

    def test_unknown_series_reports_error(self):
        """A lookup miss is reported instead of raising."""
        fake = fresh_client({"series/lookup": []})
        result = self.add_tv(fake, tvdb_id=1, tmdb_id=2, title="Nope")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ERROR)
        self.assertIn("could not find", result.message)

    def test_api_error_is_reported(self):
        """API failures are turned into a user facing message."""
        fake = fresh_client({"series": ArrError("boom", status_code=500)})
        result = self.add_tv(fake, tvdb_id=81189, tmdb_id=1396, title="BB")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ERROR)
        self.assertIn("boom", result.message)

    def test_missing_ids_cannot_be_added(self):
        """Without any external id Sonarr cannot find the show."""
        fake = fresh_client({"series/lookup": []})
        result = self.add_tv(fake, tvdb_id=None, tmdb_id=None, title="BB")

        self.assertEqual(result.outcome, sonarr.OUTCOME_ERROR)


class SonarrConfigTest(TestCase):
    """Test the Sonarr configuration resolvers."""

    def setUp(self):
        """Drop cached Sonarr status so each test sees its own responses."""
        cache.clear()

    def test_disabled_when_not_configured(self):
        """The client is None until a URL and API key are set."""
        with override_settings(SONARR_ENABLED=False):
            self.assertIsNone(sonarr.get_client())

    def test_client_is_built_from_settings(self):
        """A configured instance returns a client pointed at it."""
        with override_settings(**SONARR_SETTINGS):
            client = sonarr.get_client()
        self.assertEqual(client.base_url, "http://sonarr.test")

    def test_quality_profile_name_is_resolved(self):
        """A configured profile name resolves to its Sonarr id."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}]})
        with override_settings(**SONARR_SETTINGS):
            self.assertEqual(sonarr.resolve_quality_profile(fake), 2)

    def test_quality_profile_id_is_resolved(self):
        """A numeric profile is accepted as an id."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD"}]})
        with override_settings(**{**SONARR_SETTINGS, "SONARR_QUALITY_PROFILE": "2"}):
            self.assertEqual(sonarr.resolve_quality_profile(fake), 2)

    def test_unknown_quality_profile_lists_available(self):
        """An unknown profile names the available ones."""
        fake = FakeClient({"qualityprofile": [{"id": 2, "name": "HD - 720p/1080p"}]})
        settings = {**SONARR_SETTINGS, "SONARR_QUALITY_PROFILE": "nope"}
        with (
            override_settings(**settings),
            self.assertRaises(ArrError) as ctx,
        ):
            sonarr.resolve_quality_profile(fake)
        self.assertIn("HD - 720p/1080p", str(ctx.exception))

    def test_missing_root_folder_falls_back_to_the_first(self):
        """No configured root folder uses the first one Sonarr reports."""
        fake = FakeClient({"rootfolder": [{"id": 1, "path": "/tv"}]})
        with override_settings(**{**SONARR_SETTINGS, "SONARR_ROOT_FOLDER": ""}):
            self.assertEqual(sonarr.resolve_root_folder(fake), "/tv")

    def test_configured_root_folder_must_exist(self):
        """A configured root folder that Sonarr does not know errors out."""
        fake = FakeClient({"rootfolder": [{"id": 1, "path": "/tv"}]})
        settings = {**SONARR_SETTINGS, "SONARR_ROOT_FOLDER": "/nope"}
        with (
            override_settings(**settings),
            self.assertRaises(ArrError),
        ):
            sonarr.resolve_root_folder(fake)

    def test_language_profile_optional_on_v4(self):
        """v4 has no language profiles, so the field is left alone."""
        fake = FakeClient(
            {
                "languageprofile": [],
                "system/status": {"version": "4.0.5.1234"},
            },
        )
        with override_settings(**SONARR_SETTINGS):
            self.assertIsNone(sonarr.resolve_language_profile(fake))

    def test_language_profile_resolved_when_configured(self):
        """A configured language profile is looked up by name."""
        fake = FakeClient({"languageprofile": [{"id": 1, "name": "English"}]})
        settings = {**SONARR_SETTINGS, "SONARR_LANGUAGE_PROFILE": "English"}
        with override_settings(**settings):
            self.assertEqual(sonarr.resolve_language_profile(fake), 1)

    def test_language_profile_required_on_v3(self):
        """v3 requires a language profile, so a missing one errors out."""
        responses = {"languageprofile": [], "system/status": {"version": "3.0.9"}}
        fake = FakeClient(responses)
        with (
            override_settings(**SONARR_SETTINGS),
            self.assertRaises(ArrError) as ctx,
        ):
            sonarr.resolve_language_profile(fake)
        self.assertIn("SONARR_LANGUAGE_PROFILE", str(ctx.exception))

    def test_language_profile_endpoint_removed_is_tolerated(self):
        """A 404 on the language profile endpoint (v4) is not an error."""
        fake = FakeClient({"languageprofile": ArrError("gone", status_code=404)})
        self.assertIsNone(sonarr.language_profiles(fake))

    def test_language_profile_other_errors_propagate(self):
        """Non 404 failures on the language profile endpoint still raise."""
        fake = FakeClient({"languageprofile": ArrError("denied", status_code=401)})
        with self.assertRaises(ArrError):
            sonarr.language_profiles(fake)

    def test_is_v4_detects_the_major_version(self):
        """The version detection tolerates any version string."""
        fake = FakeClient({"system/status": {"version": "4.0.5"}})
        self.assertTrue(sonarr.is_v4(fake))

        cache.clear()
        fake = FakeClient({"system/status": {"version": "3.0.9"}})
        self.assertFalse(sonarr.is_v4(fake))

        cache.clear()
        fake = FakeClient({"system/status": {}})
        self.assertFalse(sonarr.is_v4(fake))
