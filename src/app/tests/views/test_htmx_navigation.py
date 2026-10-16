"""The contract the shell navigation relies on."""

import re
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Item, MediaTypes, Movie, Sources, Status

# Metadata for a two season show, so a season page can render its dropdown.
TV_WITH_SEASONS_METADATA = {
    "title": "Test TV Show",
    "media_type": MediaTypes.TV.value,
    "source": Sources.TMDB.value,
    "media_id": "123",
    "image": "https://example.com/tv.jpg",
    "max_progress": 2,
    "related": {
        "seasons": [
            {
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "media_id": "123",
                "season_number": 1,
                "season_title": "Season 1",
                "max_progress": 1,
                "first_air_date": "2020-01-01",
            },
            {
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "media_id": "123",
                "season_number": 2,
                "season_title": "Season 2",
                "max_progress": 1,
                "first_air_date": "2021-01-01",
            },
        ],
    },
    "season/1": {
        "title": "Test TV Show",
        "media_type": MediaTypes.SEASON.value,
        "source": Sources.TMDB.value,
        "media_id": "123",
        "season_number": 1,
        "season_title": "Season 1",
        "image": "https://example.com/s1.jpg",
        "max_progress": 1,
        "episodes": [
            {
                "episode_number": 1,
                "air_date": "2020-01-01",
                "still_path": None,
                "name": "Pilot",
                "overview": "The first one.",
                "runtime": 45,
            },
        ],
        "related": {},
    },
}


def fresh_metadata(*args, **kwargs):  # noqa: ARG001
    """Hand the view its own copy: season_details rewrites the episodes list."""
    return deepcopy(TV_WITH_SEASONS_METADATA)


# Every destination the sidebar takes an authenticated user to, as a path.
SIDEBAR_PATHS = [
    "/",
    "/create",
    "/statistics",
    "/journal",
    "/lists",
    "/calendar",
    "/settings/account",
    "/settings/preferences",
    "/settings/advanced",
    "/settings/integrations",
    "/settings/notifications",
    "/settings/import",
    "/settings/export",
    "/settings/about",
]


class ShellNavigationTest(TestCase):
    """A boosted click swaps #main-content, so that fragment must always exist."""

    def setUp(self):
        """Create a user with one movie so the sidebar lists a media type."""
        self.user = get_user_model().objects.create_user(
            username="test",
            email="test@test.com",
            password="testpass",  # noqa: S106
        )
        self.client.login(username="test", password="testpass")  # noqa: S106

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

    def test_every_page_carries_main_content(self):
        """Without the fragment the swap would be empty and the link look dead."""
        for path in SIDEBAR_PATHS:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="main-content"', response.content.decode())

        # media types that have a layout preference (exclude episode)
        layout_types = [m for m in MediaTypes.values if m != MediaTypes.EPISODE.value]
        for media_type in layout_types:
            with self.subTest(media_type=media_type):
                path = f"/test/{media_type}"
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="main-content"', response.content.decode())

    def test_the_sidebar_navigation_is_boosted(self):
        """Boosted links swap #main-content; the nav and footer follow out of band."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        nav = re.search(r'<nav id="sidebar-nav"[^>]*>', content)
        self.assertIsNotNone(nav)
        self.assertIn('hx-boost="true"', nav.group(0))
        # A tap on any sidebar link closes the mobile menu.
        self.assertIn('@click="isMobileMenuOpen = false"', nav.group(0))

        # The configuration lives once on the aside; every boosted link inside
        # inherits it, so a click never repeats it per link.
        aside = re.search(r"<aside\b[^>]*>", content)
        self.assertIsNotNone(aside)
        aside_tag = aside.group(0)
        self.assertIn('id="sidebar"', aside_tag)
        self.assertIn('hx-target="#main-content"', aside_tag)
        self.assertIn('hx-select="#main-content"', aside_tag)
        self.assertIn('hx-swap="outerHTML"', aside_tag)
        self.assertIn('hx-select-oob="#sidebar-nav,#sidebar-footer"', aside_tag)
        self.assertIn('hx-push-url="true"', aside_tag)
        self.assertIn("X-Soft-Navigation", aside_tag)

    def test_the_out_of_band_targets_never_replace_the_aside(self):
        """Swapping the aside would drop the Alpine :class that drives the menu.

        The aside owns the mobile-menu state, so only its inner nav and footer
        may be refreshed out of band.
        """
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        aside = re.search(r"<aside\b[^>]*>", content)
        self.assertIsNotNone(aside)
        oob = re.search(r'hx-select-oob="([^"]+)"', aside.group(0))
        self.assertIsNotNone(oob)

        targets = oob.group(1).split(",")
        self.assertEqual(targets, ["#sidebar-nav", "#sidebar-footer"])
        self.assertNotIn("#sidebar", targets)
        self.assertIn('id="sidebar-nav"', content)
        self.assertIn('id="sidebar-footer"', content)

    def test_the_mobile_menu_uses_a_class_binding(self):
        """x-show on the overlay is lost once content is swapped; :class is not."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        overlay = re.search(r'<div id="mobile-menu-overlay"[^>]*>', content)
        self.assertIsNotNone(overlay)
        self.assertIn(":class=\"isMobileMenuOpen ? '' : 'hidden'\"", overlay.group(0))
        self.assertNotIn("x-show", overlay.group(0))

    def test_the_settings_link_is_boosted_but_logout_is_not(self):
        """Settings sits outside the nav, so it carries its own boost."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        settings = re.search(r'<a href="/settings/account"[^>]*>', content)
        self.assertIsNotNone(settings)
        self.assertIn('hx-boost="true"', settings.group(0))

        # Logging out leaves the shell, so it must stay a plain form post.
        logout = re.search(r'<form[^>]*action="/accounts/logout/"[^>]*>', content)
        self.assertIsNotNone(logout)
        self.assertNotIn("hx-boost", logout.group(0))

    def test_a_soft_navigation_carries_both_main_content_and_sidebar(self):
        """The out-of-band swap needs the nav and footer in the response."""
        response = self.client.get(
            reverse("home"),
            headers={"HX-Request": "true", "X-Soft-Navigation": "true"},
        )
        content = response.content.decode()

        self.assertIn('id="main-content"', content)
        self.assertIn('id="sidebar"', content)
        self.assertIn('id="sidebar-nav"', content)
        self.assertIn('id="sidebar-footer"', content)

    def test_a_partial_refresh_does_not_drag_the_sidebar_along(self):
        """Only a full page carries the sidebar, so its id can never collide."""
        response = self.client.get("/test/movie", headers={"HX-Request": "true"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('id="sidebar"', content)
        self.assertNotIn('id="sidebar-nav"', content)
        self.assertNotIn('id="sidebar-footer"', content)

    def test_a_boosted_home_request_returns_the_full_page(self):
        """hx-select can only find the fragment if the page is served whole."""
        response = self.client.get(
            reverse("home"),
            headers={"HX-Request": "true", "X-Soft-Navigation": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/home.html")
        self.assertIn('id="main-content"', response.content.decode())

    def test_the_navigation_guard_is_included(self):
        """The fallback that hands non-shell responses back to the browser."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertIn("htmx-navigation.js", content)

    def test_the_alpine_sync_is_included(self):
        """Alpine must initialise the components inside a swapped fragment."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertIn("htmx-alpine.js", content)


class MediaLinkSoftNavigationTest(TestCase):
    """Opening a detail from a list is the same swap, triggered from a card."""

    def setUp(self):
        """Create a user with one tracked movie, mirroring the shell test."""
        self.user = get_user_model().objects.create_user(
            username="test",
            email="test@test.com",
            password="testpass",  # noqa: S106
        )
        self.client.login(username="test", password="testpass")  # noqa: S106

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

        self.detail_path = reverse(
            "media_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "603",
                "title": "test-movie",
            },
        )

    def _detail_link(self, content):
        """Return the anchor that points at the movie detail page."""
        match = re.search(
            rf'<a[^>]*href="{re.escape(self.detail_path)}"[^>]*>',
            content,
        )
        self.assertIsNotNone(match, "the card should link to the detail page")
        return match.group(0)

    def _assert_soft_navigation(self, tag):
        """Assert the link carries the same contract the sidebar relies on."""
        self.assertIn('hx-boost="true"', tag)
        self.assertIn('hx-target="#main-content"', tag)
        self.assertIn('hx-select="#main-content"', tag)
        self.assertIn('hx-swap="outerHTML"', tag)
        self.assertIn('hx-select-oob="#sidebar-nav,#sidebar-footer"', tag)
        self.assertIn('hx-push-url="true"', tag)
        self.assertIn("X-Soft-Navigation", tag)

    def test_a_grid_card_soft_navigates_to_the_detail(self):
        """The poster/title link must not reload the shell."""
        response = self.client.get(f"/{self.user.username}/movie?layout=grid")

        self._assert_soft_navigation(self._detail_link(response.content.decode()))

    def test_a_table_row_soft_navigates_to_the_detail(self):
        """The table title link keeps the same contract as the grid card."""
        response = self.client.get(f"/{self.user.username}/movie?layout=table")

        self._assert_soft_navigation(self._detail_link(response.content.decode()))

    def test_the_detail_page_answers_with_the_fragment(self):
        """A soft navigation needs the whole page to pick #main-content out."""
        response = self.client.get(
            self.detail_path,
            headers={"HX-Request": "true", "X-Soft-Navigation": "true"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="main-content"', content)
        self.assertIn('id="sidebar-nav"', content)
        self.assertIn('id="sidebar-footer"', content)


class TvDetailSoftNavigationTest(TestCase):
    """Drilling into a show and between its seasons is the same swap."""

    def setUp(self):
        """Log a user in; the metadata comes from a stub, not the provider."""
        self.user = get_user_model().objects.create_user(
            username="test",
            email="test@test.com",
            password="testpass",  # noqa: S106
        )
        self.client.login(username="test", password="testpass")  # noqa: S106

        self.show_path = reverse(
            "media_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.TV.value,
                "media_id": "123",
                "title": "test-tv-show",
            },
        )
        self.season_path = reverse(
            "season_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_id": "123",
                "title": "test-tv-show",
                "season_number": 1,
            },
        )
        self.other_season_path = f"{self.season_path.rsplit('/', 1)[0]}/2"

    def _assert_soft_navigation(self, content, href, expected):
        """Every anchor on that href must carry the navigation contract."""
        tags = re.findall(rf'<a[^>]*href="{re.escape(href)}"[^>]*>', content)

        self.assertEqual(len(tags), expected, href)
        for tag in tags:
            self.assertIn('hx-boost="true"', tag)
            self.assertIn('hx-target="#main-content"', tag)
            self.assertIn('hx-select="#main-content"', tag)
            self.assertIn('hx-swap="outerHTML"', tag)
            self.assertIn('hx-select-oob="#sidebar-nav,#sidebar-footer"', tag)
            self.assertIn("X-Soft-Navigation", tag)

    @patch("app.providers.services.get_media_metadata", side_effect=fresh_metadata)
    def test_the_breadcrumb_back_to_the_show_soft_navigates(self, _mock):
        """The title above a season links to its show: a detail link too."""
        response = self.client.get(self.season_path)

        self.assertEqual(response.status_code, 200)
        self._assert_soft_navigation(response.content.decode(), self.show_path, 1)

    @patch("app.providers.services.get_media_metadata", side_effect=fresh_metadata)
    def test_the_season_dropdown_soft_navigates(self, _mock):
        """Both seasons are listed, and each is the same kind of swap."""
        response = self.client.get(self.season_path)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self._assert_soft_navigation(content, self.season_path, 1)
        self._assert_soft_navigation(content, self.other_season_path, 1)


class LayoutToggleSoftNavigationTest(TestCase):
    """Switching the list layout swaps the page, filters and all."""

    def setUp(self):
        """Track one movie, so the list renders with its toolbar."""
        self.user = get_user_model().objects.create_user(
            username="test",
            email="test@test.com",
            password="testpass",  # noqa: S106
        )
        self.client.login(username="test", password="testpass")  # noqa: S106

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

        self.list_path = reverse(
            "medialist",
            kwargs={
                "username": self.user.username,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

    def _layout_link(self, content, layout):
        """Return the toolbar anchor that switches to that layout."""
        title = "Grid View" if layout == "grid" else "Table View"
        match = re.search(rf'<a[^>]*title="{title}"[^>]*>', content)

        self.assertIsNotNone(match, f"the {layout} toggle should be a link")
        return match.group(0)

    def test_the_layout_toggle_is_a_soft_navigation(self):
        """Both toggles keep the shell and hand the live filters to the server."""
        response = self.client.get(f"{self.list_path}?layout=grid")
        content = response.content.decode()

        for layout in ("grid", "table"):
            with self.subTest(layout=layout):
                tag = self._layout_link(content, layout)

                # hx-get, not hx-boost: boost reads the href only once, when
                # htmx processes the node, so it would send the filters of the
                # last full page load instead of the ones on screen now.
                self.assertNotIn("hx-boost", tag)
                self.assertIn(f'hx-get="{self.list_path}"', tag)
                self.assertIn('hx-include="#filter-form"', tag)
                self.assertIn(f"&quot;layout&quot;: &quot;{layout}&quot;", tag)

                self.assertIn('hx-target="#main-content"', tag)
                self.assertIn('hx-select="#main-content"', tag)
                self.assertIn('hx-swap="outerHTML"', tag)
                self.assertIn('hx-select-oob="#sidebar-nav,#sidebar-footer"', tag)
                self.assertIn('hx-push-url="true"', tag)
                self.assertIn("X-Soft-Navigation", tag)

    def test_the_layout_toggle_keeps_a_real_href(self):
        """A browser without htmx can still follow the anchor."""
        response = self.client.get(f"{self.list_path}?layout=grid")

        self.assertIn(
            f'href="{self.list_path}?layout=grid"',
            response.content.decode(),
        )

    def test_a_layout_change_can_be_reloaded(self):
        """The pushed URL has to reproduce the page it came from."""
        response = self.client.get(f"{self.list_path}?layout=table")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<tbody>", content)
        self.assertNotIn('class="media-grid"', content)
