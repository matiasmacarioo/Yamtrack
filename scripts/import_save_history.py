"""Import games discovered from local save backups into Yamtrack.

Runs INSIDE the container so it writes to the live database and resolves
titles through IGDB exactly like the built-in importers do.

Usage:
    docker cp save_history.json yamtrack:/tmp/pc_games.json
    docker cp scripts/import_save_history.py yamtrack:/tmp/
    docker exec -e YAMTRACK_USER=matias yamtrack python /tmp/import_save_history.py

Environment:
    YAMTRACK_USER       username to import for (required)
    YAMTRACK_DATA       manifest path (default /tmp/pc_games.json)
    RECENT_DAYS         last save within N days -> In progress (default 90)
    DRY_RUN=1           resolve and report without writing anything
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, "/yamtrack")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from app.mixins import disable_fetch_releases  # noqa: E402
from app.models import Game, Item, MediaTypes, Sources, Status  # noqa: E402
from app.providers import services  # noqa: E402
from integrations.imports.helpers import bulk_create_media  # noqa: E402

DATA = os.environ.get("YAMTRACK_DATA", "/tmp/pc_games.json")
USERNAME = os.environ.get("YAMTRACK_USER")
RECENT_DAYS = int(os.environ.get("RECENT_DAYS", "90"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"
MAX_RETRIES = 5

if not USERNAME:
    sys.exit("Set YAMTRACK_USER to the Yamtrack username to import for.")

user = get_user_model().objects.get(username=USERNAME)
rows = json.load(open(DATA, encoding="utf-8"))
existing = set(
    Game.objects.filter(user=user).values_list("item__media_id", "item__source")
)

created, skipped, unmatched = [], [], []
instances = []
now = timezone.now()


def search_with_retry(title):
    """Search IGDB, waiting out 429 throttling (it can be aggressive)."""
    for attempt in range(MAX_RETRIES):
        try:
            return services.search("game", title, 1).get("results", [])
        except Exception as error:  # noqa: BLE001
            text = str(error)
            if "429" in text or "Too Many Requests" in text:
                wait = 15 * (attempt + 1)
                print(
                    f"    rate limited, waiting {wait}s ({attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue
            raise
    return []


with disable_fetch_releases():
    for row in rows:
        title = row["title"]
        try:
            results = search_with_retry(title)
        except Exception as error:  # noqa: BLE001
            unmatched.append(f"{title} (search error: {error})")
            continue

        if not results:
            unmatched.append(title)
            continue

        match = results[0]
        media_id = str(match["media_id"])

        if (media_id, Sources.IGDB.value) in existing:
            skipped.append(f"{title}  ->  {match['title']} (already tracked)")
            continue

        first = datetime.fromisoformat(row["first"])
        last = datetime.fromisoformat(row["last"])
        # The scanner emits local time; make it aware whether or not it already is.
        first = first if first.tzinfo else timezone.make_aware(first)
        last = last if last.tzinfo else timezone.make_aware(last)
        recent = last >= now - timedelta(days=RECENT_DAYS)
        status = Status.IN_PROGRESS if recent else Status.PAUSED

        if DRY_RUN:
            created.append(f"[dry run] {title} -> {match['title']} [{status.label}]")
            existing.add((media_id, Sources.IGDB.value))
            continue

        item, _ = Item.objects.get_or_create(
            media_id=media_id,
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            defaults={"title": match["title"], "image": match["image"]},
        )

        instance = Game(
            item=item,
            user=user,
            progress=0,  # save files don't carry playtime
            status=status.value,
            start_date=first,
            end_date=last,
            notes=(
                f"Imported from local save backups ({row['files']} save files). "
                f"First save {first:%Y-%m-%d}, last save {last:%Y-%m-%d}."
            ),
        )
        # Dated history entry so the journal/heatmap shows the real play dates.
        instance._history_date = last

        instances.append(instance)
        existing.add((media_id, Sources.IGDB.value))
        created.append(
            f"{title}  ->  {match['title']}  [{status.label}]  "
            f"{first:%Y-%m-%d} .. {last:%Y-%m-%d}",
        )
        time.sleep(0.3)  # stay under IGDB's rate limit

if instances:
    bulk_create_media({MediaTypes.GAME.value: instances}, user)

print(f"\n=== CREATED ({len(created)}) ===")
for line in created:
    print(" ", line)
print(f"\n=== ALREADY TRACKED, LEFT ALONE ({len(skipped)}) ===")
for line in skipped:
    print(" ", line)
print(f"\n=== NO IGDB MATCH ({len(unmatched)}) ===")
for line in unmatched:
    print(" ", line)
print(
    f"\nSummary: {len(created)} created, {len(skipped)} skipped, "
    f"{len(unmatched)} unmatched."
)
