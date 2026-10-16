"""End-to-end check of the boosted shell navigation on a phone-sized viewport.

A boosted tap must swap #main-content in place, let the sidebar highlight follow
through the out-of-band swap, and leave the Alpine-driven mobile menu working.
"""

import os
import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from app.models import Item, MediaTypes, Movie, Sources, Status


def launch_browser(playwright):
    """Prefer the managed Chromium, fall back to a locally installed Chrome."""
    try:
        return playwright.chromium.launch()
    except Exception:  # noqa: BLE001 - the browser just is not installed here
        return playwright.chromium.launch(channel="chrome")


class SoftNavigationTest(StaticLiveServerTestCase):
    """The shell must survive a boosted tap with the menu still usable."""

    @classmethod
    def setUpClass(cls):
        """Boot a phone-sized browser once for the whole class."""
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = launch_browser(cls.playwright)
        cls.context = cls.browser.new_context(viewport={"width": 400, "height": 800})
        cls.page = cls.context.new_page()

    @classmethod
    def tearDownClass(cls):
        """Shut the browser down."""
        cls.context.close()
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        """Track one movie so the sidebar lists a media type to click."""
        self.credentials = {"username": "test", "password": "testpass"}
        self.user = get_user_model().objects.create_user(**self.credentials)

        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        self.page.goto(f"{self.live_server_url}/")
        self.page.get_by_placeholder("Enter your username").fill(
            self.credentials["username"],
        )
        self.page.get_by_placeholder("Enter your password").fill(
            self.credentials["password"],
        )
        self.page.get_by_role("button", name="Sign in").click()
        expect(self.page.locator("#main-content")).to_be_visible()

    def open_menu(self):
        """Tap the hamburger and wait for the overlay to show."""
        self.page.click("#mobile-menu-toggle")
        expect(self.page.locator("#mobile-menu-overlay")).to_be_visible()

    def test_a_boosted_tap_replaces_the_main_content_in_place(self):
        """The swap must not reload the document nor nest a second shell."""
        self.open_menu()
        self.page.evaluate("window.__softNavSentinel = 42")

        self.page.click('#sidebar-nav a[href="/test/movie"]')

        # The media list is the only page carrying the filter form.
        expect(self.page.locator("#filter-form")).to_be_attached()
        # hx-push-url keeps the address bar shareable.
        expect(self.page).to_have_url(f"{self.live_server_url}/test/movie")
        # A full page load would have wiped the sentinel.
        self.assertEqual(self.page.evaluate("window.__softNavSentinel"), 42)
        # outerHTML, not innerHTML: the container must not be nested.
        self.assertEqual(self.page.locator("#main-content").count(), 1)

    def test_the_sidebar_highlight_follows_a_boosted_tap(self):
        """The out-of-band nav swap is what moves the active highlight."""
        self.open_menu()
        home = self.page.locator('#sidebar-nav a[href="/"]')
        movies = self.page.locator('#sidebar-nav a[href="/test/movie"]')

        expect(home).to_have_class(re.compile(r"\btext-white\b"))

        self.page.click('#sidebar-nav a[href="/test/movie"]')

        expect(movies).to_have_class(re.compile(r"\btext-white\b"))
        expect(home).to_have_class(re.compile(r"\btext-gray-400\b"))

    def test_the_mobile_menu_closes_on_tap_and_reopens(self):
        """The aside keeps its Alpine :class, so the menu is usable again."""
        self.open_menu()

        self.page.click('#sidebar-nav a[href="/test/movie"]')

        expect(self.page.locator("#filter-form")).to_be_attached()
        expect(self.page.locator("#mobile-menu-overlay")).to_be_hidden()

        self.page.click("#mobile-menu-toggle")
        expect(self.page.locator("#mobile-menu-overlay")).to_be_visible()

    def test_the_settings_link_is_boosted(self):
        """Settings sits outside the nav and soft-navigates on its own."""
        self.open_menu()
        self.page.evaluate("window.__softNavSentinel = 7")

        self.page.click('#sidebar-footer a[href="/settings/account"]')

        expect(self.page).to_have_url(f"{self.live_server_url}/settings/account")
        self.assertEqual(self.page.evaluate("window.__softNavSentinel"), 7)
        # The footer is refreshed out of band, so its highlight follows too.
        expect(
            self.page.locator('#sidebar-footer a[href="/settings/account"]'),
        ).to_have_class(re.compile(r"\btext-white\b"))

    def test_a_card_link_soft_navigates_to_the_detail(self):
        """Opening a detail from a list is the same swap, from another link."""
        detail_path = "/details/tmdb/movie/603/test-movie"
        self.page.goto(f"{self.live_server_url}/test/movie")
        self.page.evaluate("window.__softNavSentinel = 99")

        # The title anchor sits below the hover overlay, so the tap is reliable.
        with self.page.expect_request(
            lambda request: detail_path in request.url,
        ) as request_info:
            self.page.locator(f'#main-content a[href="{detail_path}"]').last.click()

        # htmx must unescape the entity-encoded JSON in hx-headers, otherwise
        # the server would mistake this navigation for a fragment fetch.
        headers = request_info.value.headers
        self.assertEqual(headers.get("hx-request"), "true")
        self.assertEqual(headers.get("x-soft-navigation"), "true")

        expect(self.page).to_have_url(f"{self.live_server_url}{detail_path}")
        # A full page load would have wiped the sentinel.
        self.assertEqual(self.page.evaluate("window.__softNavSentinel"), 99)
        # outerHTML, not innerHTML: the shell is never duplicated.
        self.assertEqual(self.page.locator("#main-content").count(), 1)
        self.assertEqual(self.page.locator("#sidebar-nav").count(), 1)
