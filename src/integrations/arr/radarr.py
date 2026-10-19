"""Radarr integration behind the "Add to Radarr" action."""

import logging

from django.conf import settings

from integrations.arr.client import ArrClient, ArrError

logger = logging.getLogger(__name__)

PROVIDER = "Radarr"
MAX_LOOKUP_RESULTS = 20
OUTCOME_ADDED = "added"
OUTCOME_UPDATED = "updated"
OUTCOME_ALREADY = "already"
OUTCOME_ERROR = "error"

# Radarr refuses to add a movie without a minimum availability, so a default
# is applied whenever the environment does not set one.
DEFAULT_MINIMUM_AVAILABILITY = "released"


class ArrResult:
    """Outcome of an "Add to Radarr" request."""

    def __init__(self, outcome, message):
        """Set the outcome (added, updated, already, error) and its message."""
        self.outcome = outcome
        self.message = message


def get_client():
    """Return a configured Radarr client, or None when Radarr is disabled."""
    if not settings.RADARR_ENABLED:
        return None
    return ArrClient(settings.RADARR_URL, settings.RADARR_API_KEY)


def quality_profiles(client):
    """Return the quality profiles configured in Radarr."""
    return client.get("qualityprofile") or []


def root_folders(client):
    """Return the root folders configured in Radarr."""
    return client.get("rootfolder") or []


def resolve_quality_profile(client):
    """Return the configured quality profile id, resolving its name if needed."""
    value = str(settings.RADARR_QUALITY_PROFILE or "").strip()
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

    value = str(settings.RADARR_ROOT_FOLDER or "").strip()
    if not value:
        return folders[0]["path"]

    for folder in folders:
        if _normalize_path(folder["path"]) == _normalize_path(value):
            return folder["path"]

    paths = ", ".join(folder["path"] for folder in folders)
    msg = f"Root folder {value!r} was not found in {PROVIDER}. Available: {paths}."
    raise ArrError(msg)


def resolve_minimum_availability():
    """Return the configured minimum availability, defaulting to released."""
    value = str(settings.RADARR_MINIMUM_AVAILABILITY or "").strip()
    return value or DEFAULT_MINIMUM_AVAILABILITY


def find_movie(client, tmdb_id, imdb_id):
    """Return the movie already imported in Radarr, matched by external id."""
    for movie in client.get("movie") or []:
        if tmdb_id and movie.get("tmdbId") == tmdb_id:
            return movie
        if imdb_id and movie.get("imdbId") == imdb_id:
            return movie
    return None


def lookup_movie(client, tmdb_id, imdb_id):
    """Return the Radarr metadata for the movie, searched by TMDB then IMDb."""
    terms = []
    if tmdb_id:
        terms.append(f"tmdb:{tmdb_id}")
    if imdb_id:
        terms.append(f"imdb:{imdb_id}")

    for term in terms:
        results = client.get("movie/lookup", params={"term": term}) or []
        for result in results[:MAX_LOOKUP_RESULTS]:
            if tmdb_id and result.get("tmdbId") == tmdb_id:
                return result
            if imdb_id and result.get("imdbId") == imdb_id:
                return result
        if len(results) == 1:
            return results[0]
    return None


def run_command(client, name, **payload):
    """Trigger a Radarr command."""
    body = {"name": name, **payload}
    logger.info("%s command: %s", PROVIDER, body)
    return client.post("command", body)


def queue_search(client, movie_id):
    """Queue a search for the missing releases of a movie."""
    return run_command(client, "MoviesSearch", movieIds=[movie_id])


def add_movie(*, tmdb_id=None, imdb_id=None, title="the movie", search=False):
    """Add a movie to Radarr.

    Returns an ArrResult; failures are reported instead of raised so that the
    view can turn them into a user facing message.
    """
    client = get_client()
    if client is None:
        msg = f"{PROVIDER} is not configured on this instance."
        return ArrResult(OUTCOME_ERROR, msg)

    try:
        return _add_movie(client, tmdb_id, imdb_id, title, search)
    except ArrError as error:
        logger.warning("Add to %s failed for %s: %s", PROVIDER, title, error)
        return ArrResult(OUTCOME_ERROR, str(error))


def _add_movie(client, tmdb_id, imdb_id, title, search):
    existing = find_movie(client, tmdb_id, imdb_id)
    if existing is not None:
        return _monitor_movie(client, existing, search)

    info = lookup_movie(client, tmdb_id, imdb_id)
    if info is None:
        msg = (
            f"{PROVIDER} could not find {title!r} for TMDB/IMDb id {tmdb_id}/{imdb_id}."
        )
        raise ArrError(msg)

    info["qualityProfileId"] = resolve_quality_profile(client)
    info["rootFolderPath"] = resolve_root_folder(client)
    info["minimumAvailability"] = resolve_minimum_availability()
    info["monitored"] = True
    info["addOptions"] = {"searchForMovie": False}

    created = client.post("movie", info)
    movie_id = (created or {}).get("id")
    if not movie_id:
        msg = f"{PROVIDER} did not return a movie id for {title}."
        raise ArrError(msg)

    message = f"{title} was added to {PROVIDER}."
    if search:
        queue_search(client, movie_id)
        message += " A search was queued."

    logger.info("%s", message)
    return ArrResult(OUTCOME_ADDED, message)


def _monitor_movie(client, existing, search):
    movie_id = existing.get("id")
    title = existing.get("title", "the movie")

    if existing.get("monitored"):
        message = f"{title} is already in {PROVIDER}."
        if search:
            queue_search(client, movie_id)
            message += " A search was queued."
        return ArrResult(OUTCOME_ALREADY, message)

    client.put(f"movie/{movie_id}", {**existing, "monitored": True})
    message = f"{title} is now monitored in {PROVIDER}."
    if search:
        queue_search(client, movie_id)
        message += " A search was queued."

    logger.info("%s", message)
    return ArrResult(OUTCOME_UPDATED, message)
