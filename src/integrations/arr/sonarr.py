"""Sonarr integration behind the "Add to Sonarr" action."""

import logging

from django.conf import settings
from django.core.cache import cache

from integrations.arr.client import ArrClient, ArrError

logger = logging.getLogger(__name__)

PROVIDER = "Sonarr"
SYSTEM_STATUS_CACHE_KEY = "sonarr_system_status"
RESOLVE_CACHE_TIMEOUT = 60 * 60
MAX_LOOKUP_RESULTS = 20
OUTCOME_ADDED = "added"
OUTCOME_UPDATED = "updated"
OUTCOME_ALREADY = "already"
OUTCOME_ERROR = "error"


SONARR_V4_MIN_MAJOR = 4
HTTP_NOT_FOUND = 404


class ArrResult:
    """Outcome of an "Add to Sonarr" request."""

    def __init__(self, outcome, message):
        """Set the outcome (added, updated, already, error) and its message."""
        self.outcome = outcome
        self.message = message


def get_client():
    """Return a configured Sonarr client, or None when Sonarr is disabled."""
    if not settings.SONARR_ENABLED:
        return None
    return ArrClient(settings.SONARR_URL, settings.SONARR_API_KEY)


def system_status(client):
    """Return the cached Sonarr system status."""
    status = cache.get(SYSTEM_STATUS_CACHE_KEY)
    if status is None:
        status = client.get("system/status")
        cache.set(SYSTEM_STATUS_CACHE_KEY, status, RESOLVE_CACHE_TIMEOUT)
    return status or {}


def is_v4(client):
    """Return True when the connected instance runs Sonarr v4 or newer."""
    version = str(system_status(client).get("version", "3"))
    try:
        return int(version.split(".", maxsplit=1)[0]) >= SONARR_V4_MIN_MAJOR
    except ValueError:
        return False


def quality_profiles(client):
    """Return the quality profiles configured in Sonarr."""
    return client.get("qualityprofile") or []


def root_folders(client):
    """Return the root folders configured in Sonarr."""
    return client.get("rootfolder") or []


def language_profiles(client):
    """Return the language profiles, or None when the endpoint is missing."""
    try:
        return client.get("languageprofile")
    except ArrError as error:
        if error.status_code == HTTP_NOT_FOUND:
            return None
        raise


def resolve_quality_profile(client):
    """Return the configured quality profile id, resolving its name if needed."""
    value = str(settings.SONARR_QUALITY_PROFILE or "").strip()
    profiles = quality_profiles(client)
    if not profiles:
        msg = f"{PROVIDER} has no quality profiles configured."
        raise ArrError(msg)

    if value.isdigit():
        if any(str(profile["id"]) == value for profile in profiles):
            return int(value)
    else:
        for profile in profiles:
            if profile["name"].casefold() == value.casefold():
                return profile["id"]

    names = ", ".join(profile["name"] for profile in profiles)
    msg = f"Quality profile {value!r} was not found in {PROVIDER}. Available: {names}."
    raise ArrError(msg)


def _normalize_path(path):
    """Normalize a folder path for comparison (slash style, trailing slash)."""
    return str(path).replace("\\", "/").rstrip("/").casefold()


def resolve_root_folder(client):
    """Return the configured root folder path, defaulting to the first one."""
    folders = root_folders(client)
    if not folders:
        msg = f"{PROVIDER} has no root folders configured."
        raise ArrError(msg)

    value = str(settings.SONARR_ROOT_FOLDER or "").strip()
    if not value:
        return folders[0]["path"]

    for folder in folders:
        if _normalize_path(folder["path"]) == _normalize_path(value):
            return folder["path"]

    paths = ", ".join(folder["path"] for folder in folders)
    msg = f"Root folder {value!r} was not found in {PROVIDER}. Available: {paths}."
    raise ArrError(msg)


def resolve_language_profile(client):
    """Return the language profile id on v3, or None when it is not required."""
    profiles = language_profiles(client)
    if profiles is None:  # endpoint removed in v4
        return None

    value = str(settings.SONARR_LANGUAGE_PROFILE or "").strip()
    if not value:
        if is_v4(client):
            return None
        msg = f"{PROVIDER} v3 requires SONARR_LANGUAGE_PROFILE to be set."
        raise ArrError(msg)

    for profile in profiles:
        if str(profile["name"]).casefold() == value.casefold():
            return profile["id"]

    if value.isdigit():
        return int(value)

    names = ", ".join(profile["name"] for profile in profiles)
    msg = f"Language profile {value!r} was not found in {PROVIDER}. Available: {names}."
    raise ArrError(msg)


def find_series(client, tvdb_id, tmdb_id):
    """Return the series already imported in Sonarr, matched by external id."""
    for series in client.get("series") or []:
        if tvdb_id and series.get("tvdbId") == tvdb_id:
            return series
        if tmdb_id and series.get("tmdbId") == tmdb_id:
            return series
    return None


def lookup_series(client, tvdb_id, tmdb_id):
    """Return the Sonarr metadata for the series, searched by TVDB then TMDB."""
    terms = []
    if tvdb_id:
        terms.append(f"tvdb:{tvdb_id}")
    if tmdb_id:
        terms.append(f"tmdb:{tmdb_id}")

    for term in terms:
        results = client.get("series/lookup", params={"term": term}) or []
        for result in results[:MAX_LOOKUP_RESULTS]:
            if tvdb_id and result.get("tvdbId") == tvdb_id:
                return result
            if tmdb_id and result.get("tmdbId") == tmdb_id:
                return result
        if len(results) == 1:
            return results[0]
    return None


def monitored_seasons(series):
    """Return the numbers of the seasons currently monitored in Sonarr."""
    return {
        season["seasonNumber"]
        for season in series.get("seasons") or []
        if season.get("monitored")
    }


def mark_seasons(series, seasons_to_monitor):
    """Return the series seasons with the monitored flags applied."""
    return [
        {
            **season,
            "monitored": season["seasonNumber"] in seasons_to_monitor,
        }
        for season in series.get("seasons") or []
    ]


def run_command(client, name, **payload):
    """Trigger a Sonarr command."""
    body = {"name": name, **payload}
    logger.info("%s command: %s", PROVIDER, body)
    return client.post("command", body)


def set_monitored_seasons(client, series_id, seasons_to_monitor):
    """Monitor exactly the given seasons of a series already in Sonarr.

    Sonarr cascades the season flags to their episodes, which is what makes
    those episodes grabbable.
    """
    series = client.get(f"series/{series_id}") or {}
    client.put(
        f"series/{series_id}",
        {**series, "seasons": mark_seasons(series, seasons_to_monitor)},
    )


def queue_search(client, series_id, season_number=None):
    """Queue a search for the missing episodes of a series or one season."""
    if season_number is None:
        return run_command(client, "SeriesSearch", seriesId=series_id)
    return run_command(
        client,
        "SeasonSearch",
        seriesId=series_id,
        seasonNumber=season_number,
    )


def add_tv(*, tvdb_id, tmdb_id, title, season_number=None, search=False):
    """Add a TV show, or a single season of it, to Sonarr.

    Returns an ArrResult; failures are reported instead of raised so that the
    view can turn them into a user facing message.
    """
    client = get_client()
    if client is None:
        msg = f"{PROVIDER} is not configured on this instance."
        return ArrResult(OUTCOME_ERROR, msg)

    try:
        return _add_tv(client, tvdb_id, tmdb_id, title, season_number, search)
    except ArrError as error:
        logger.warning("Add to %s failed for %s: %s", PROVIDER, title, error)
        return ArrResult(OUTCOME_ERROR, str(error))


def _add_tv(client, tvdb_id, tmdb_id, title, season_number, search):
    existing = find_series(client, tvdb_id, tmdb_id)
    if existing is not None:
        return _monitor_season(client, existing, season_number, search)

    info = lookup_series(client, tvdb_id, tmdb_id)
    if info is None:
        msg = (
            f"{PROVIDER} could not find {title!r} for TVDB/TMDB id {tvdb_id}/{tmdb_id}."
        )
        raise ArrError(msg)

    info["qualityProfileId"] = resolve_quality_profile(client)
    info["rootFolderPath"] = resolve_root_folder(client)
    language_profile_id = resolve_language_profile(client)
    if language_profile_id is not None:
        info["languageProfileId"] = language_profile_id
    info["monitored"] = True
    info["addOptions"] = {
        "monitor": "all" if season_number is None else "none",
        "searchForMissingEpisodes": False,
    }

    created = client.post("series", info)
    series_id = (created or {}).get("id")
    if not series_id:
        msg = f"{PROVIDER} did not return a series id for {title}."
        raise ArrError(msg)

    if season_number is None:
        # "all" monitors every season but the specials, and Sonarr cascades
        # that to the episodes, so the show can be grabbed.
        message = f"{title} was added to {PROVIDER}."
    else:
        # Sonarr's monitor presets cannot express "only this season", so the
        # season flags are applied explicitly afterwards. The add alone leaves
        # the episodes unmonitored, which would prevent any grab.
        message = f"{title} season {season_number} was added to {PROVIDER}."
        set_monitored_seasons(client, series_id, {season_number})

    if search:
        queue_search(client, series_id, season_number)
        message += " A search was queued."

    logger.info("%s", message)
    return ArrResult(OUTCOME_ADDED, message)


def _monitor_season(client, existing, season_number, search):
    series_id = existing.get("id")
    title = existing.get("title", "the series")
    current = monitored_seasons(existing)

    if season_number is None:
        message = f"{title} is already in {PROVIDER}."
        if search:
            queue_search(client, series_id)
            message += " A search was queued."
        return ArrResult(OUTCOME_ALREADY, message)

    if season_number in current:
        message = f"{title} season {season_number} is already monitored."
        if search:
            queue_search(client, series_id, season_number)
            message += " A search was queued."
        return ArrResult(OUTCOME_ALREADY, message)

    client.put(
        f"series/{series_id}",
        {**existing, "seasons": mark_seasons(existing, current | {season_number})},
    )
    message = f"{title} season {season_number} is now monitored."
    if search:
        queue_search(client, series_id, season_number)
        message += " A search was queued."

    logger.info("%s", message)
    return ArrResult(OUTCOME_UPDATED, message)
