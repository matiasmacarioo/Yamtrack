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

    def test_only_the_home_link_is_boosted_for_now(self):
        """Step 1 migrates a single link; the contract lives on that anchor."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()

        anchors = re.findall(r"<a\b[^>]*>", content)
        boosted = [anchor for anchor in anchors if "hx-boost" in anchor]

        self.assertEqual(len(boosted), 1, "only the Home link should be boosted")
        link = boosted[0]

        # it still points at the real URL, so it works without JavaScript
        self.assertIn('href="/"', link)
        self.assertIn('hx-boost="true"', link)
        self.assertIn('hx-target="#main-content"', link)
        self.assertIn('hx-select="#main-content"', link)
        self.assertIn('hx-swap="outerHTML"', link)
        self.assertIn('hx-push-url="true"', link)
        self.assertIn("X-Soft-Navigation", link)

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
