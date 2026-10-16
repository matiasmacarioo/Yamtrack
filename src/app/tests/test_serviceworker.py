from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def _serviceworker_source() -> str:
    """Return the source of the built-in service worker."""
    return (Path(settings.STATICFILES_DIRS[0]) / "js" / "serviceworker.js").read_text(
        encoding="utf-8"
    )


class ServiceWorkerTest(SimpleTestCase):
    """The service worker must never serve a stale application shell."""

    def test_html_pages_are_not_pre_cached(self):
        """Pre-caching '/' froze the whole UI behind an outdated shell."""
        source = _serviceworker_source()
        _, _, pre_cache = source.partition("STATIC_ASSETS")
        pre_cache = pre_cache.partition("]")[0]

        # the root document must never be part of the pre-cache list
        self.assertNotIn("'/'", pre_cache)
        self.assertNotIn('"/"', pre_cache)
        self.assertIn("/static/", pre_cache)

    def test_navigations_are_network_first(self):
        """A cached navigation would hide new templates and scripts."""
        source = _serviceworker_source()
        self.assertIn("request.mode === 'navigate'", source)

    def test_new_version_takes_over_immediately(self):
        """SkipWaiting plus clients.claim avoid a stale worker sticking around."""
        source = _serviceworker_source()
        self.assertIn("self.skipWaiting()", source)
        self.assertIn("self.clients.claim()", source)
