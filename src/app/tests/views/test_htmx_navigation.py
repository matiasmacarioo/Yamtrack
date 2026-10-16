"""The contract the shell navigation relies on."""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Item, MediaTypes, Movie, Sources, Status

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
