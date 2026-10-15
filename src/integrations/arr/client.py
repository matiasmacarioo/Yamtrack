"""HTTP client shared by the *arr integrations (Sonarr, Radarr)."""

import logging

import requests

logger = logging.getLogger(__name__)

API_VERSION = "v3"
REQUEST_TIMEOUT = 15


class ArrError(Exception):
    """Raised when a request against a *arr service fails."""

    def __init__(self, message, status_code=None):
        """Store the error message and the HTTP status code when available."""
        super().__init__(message)
        self.status_code = status_code


class ArrClient:
    """Minimal client for the *arr v3 REST API."""

    def __init__(self, base_url, api_key, api_version=API_VERSION):
        """Configure the service base URL, the API key and the API version."""
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    def url(self, path):
        """Return the absolute URL for an API path."""
        return f"{self.base_url}/api/{self.api_version}/{path.lstrip('/')}"

    def request(self, method, path, **kwargs):
        """Perform a request and return the decoded JSON response, if any."""
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        url = self.url(path)
        logger.debug("arr %s %s", method, url)

        try:
            response = self.session.request(method, url, **kwargs)
        except requests.exceptions.RequestException as error:
            msg = f"Could not reach the service at {self.base_url}: {error}"
            raise ArrError(msg) from error

        if not response.ok:
            msg = (
                f"{method} {path} failed with HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            raise ArrError(msg, status_code=response.status_code)

        if not response.content:
            return None
        return response.json()

    def get(self, path, params=None):
        """Perform a GET request."""
        return self.request("GET", path, params=params)

    def post(self, path, payload=None):
        """Perform a POST request sending a JSON payload."""
        return self.request("POST", path, json=payload)

    def put(self, path, payload=None):
        """Perform a PUT request sending a JSON payload."""
        return self.request("PUT", path, json=payload)
