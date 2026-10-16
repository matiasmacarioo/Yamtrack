"""Guard against template comments leaking into the rendered page."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.TEMPLATES[0]["DIRS"][0])

# Django's {# ... #} comment must open and close on the same line. A multi-line
# one is not recognised by the template lexer, so it is printed verbatim and
# shows up in the UI. The lookbehind skips Handlebars-style {{#if ...}} blocks,
# which live inside {% verbatim %} and only look like an opening brace-pair.
_OPEN = re.compile(r"(?<!\{)\{#")
_CLOSE = re.compile(r"#\}")


class TemplateCommentTest(SimpleTestCase):
    """A {# #} comment must never span more than one line."""

    def test_no_multiline_tag_comments(self):
        """Multi-line {# #} comments render as literal text on the page."""
        offenders = []
        for path in TEMPLATES_DIR.rglob("*.html"):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = _OPEN.search(line)
                if match and not _CLOSE.search(line, match.end()):
                    relative = path.relative_to(TEMPLATES_DIR)
                    offenders.append(f"{relative}:{lineno}")

        self.assertEqual(
            offenders,
            [],
            "these {# #} comments span multiple lines and would render as "
            "visible text: " + ", ".join(offenders),
        )
