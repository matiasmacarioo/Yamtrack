"""Scan local game-save copies and build a play-history JSON for Yamtrack.

Sources:
  - a ludusavi backup folder (--backup, default %USERPROFILE%\\ludusavi-backup)
  - curated game folders under Documents / Saved Games (see EXTRAS below)

Dates come from file modification times, which ludusavi preserves.

Usage:
    python scripts/build_save_history.py [--backup DIR] [--user NAME] [--out FILE]

The default output is ./save_history.json, which you then hand to
scripts/import_save_history.py inside the container.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--backup",
    default=str(Path(os.environ.get("USERPROFILE", Path.home())) / "ludusavi-backup"),
    help="ludusavi backup folder to scan",
)
parser.add_argument(
    "--user",
    default=os.environ.get("USERPROFILE", str(Path.home())),
    help="user profile folder holding Documents and Saved Games",
)
parser.add_argument("--out", default="save_history.json", help="JSON file to write")
args = parser.parse_args()

USERPROFILE = Path(args.user)
BACKUP = Path(args.backup)
DOCS = USERPROFILE / "Documents"
SAVED_GAMES = USERPROFILE / "Saved Games"
OUT = Path(args.out)

# Files ludusavi writes itself at backup time; they carry no play signal.
SKIP_FILES = {"mapping.yaml"}

# Explicit game folders on this PC that the ludusavi backup may not cover,
# mapped to the title Yamtrack/IGDB should search for.
EXTRAS = [
    (
        SAVED_GAMES / "Uncharted Legacy of Thieves Collection",
        "Uncharted: Legacy of Thieves Collection",
    ),
    (DOCS / "Assassin's Creed Mirage", "Assassin's Creed Mirage"),
    (DOCS / "ACE", "Assetto Corsa"),
    (DOCS / "acs", "Assetto Corsa"),
    (DOCS / "Assetto Corsa", "Assetto Corsa"),
    (DOCS / "Assetto Corsa Competizione", "Assetto Corsa Competizione"),
    (DOCS / "Battlefield 6", "Battlefield 6"),
    (DOCS / "Call of Duty Modern Warfare", "Call of Duty: Modern Warfare"),
    (DOCS / "Call of Duty MWIII", "Call of Duty: Modern Warfare III"),
    (DOCS / "Call of Duty Vanguard", "Call of Duty: Vanguard"),
    (DOCS / "CD Projekt Red" / "Cyberpunk 2077", "Cyberpunk 2077"),
    (DOCS / "Ghost of Tsushima DIRECTOR'S CUT", "Ghost of Tsushima Director's Cut"),
    (DOCS / "Hogwarts Legacy", "Hogwarts Legacy"),
    (
        DOCS / "Horizon Forbidden West Complete Edition",
        "Horizon Forbidden West Complete Edition",
    ),
    (DOCS / "KoeiTecmo" / "Ronin", "Rise of the Ronin"),
    (DOCS / "Marvel's Spider-Man 2", "Marvel's Spider-Man 2"),
    (DOCS / "My Games" / "A Plague Tale Requiem", "A Plague Tale: Requiem"),
    (DOCS / "My Games" / "BladeAndSorcery", "Blade & Sorcery"),
    (DOCS / "My Games" / "DiRT Rally 2.0", "DiRT Rally 2.0"),
    (DOCS / "My Games" / "F1 22", "F1 22"),
    (DOCS / "My Games" / "F1 25", "F1 25"),
    (DOCS / "My Games" / "Skyrim VR", "The Elder Scrolls V: Skyrim VR"),
    (DOCS / "My Games" / "SpecOps-TheLine", "Spec Ops: The Line"),
    (DOCS / "Respawn" / "Titanfall2", "Titanfall 2"),
    (DOCS / "Rockstar Games" / "GTA V", "Grand Theft Auto V"),
    (DOCS / "Rockstar Games" / "GTAV Enhanced", "Grand Theft Auto V Enhanced"),
    (DOCS / "Rockstar Games" / "Red Dead Redemption 2", "Red Dead Redemption 2"),
    (DOCS / "The Last of Us Part II", "The Last of Us Part II"),
    (DOCS / "The Witcher 3", "The Witcher 3: Wild Hunt"),
]

entries = {}


def add(path, title):
    """Fold one folder's save files into the title's date range."""
    first = last = None
    count = 0
    for f in path.rglob("*"):
        if not f.is_file() or f.name.lower() in SKIP_FILES:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).astimezone()
        except OSError:
            continue
        count += 1
        if first is None or mtime < first:
            first = mtime
        if last is None or mtime > last:
            last = mtime

    if not count:
        return

    entry = entries.setdefault(
        title,
        {"title": title, "first": first, "last": last, "files": count, "origins": []},
    )
    entry["origins"].append(str(path))
    if first < entry["first"]:
        entry["first"] = first
    if last > entry["last"]:
        entry["last"] = last
    entry["files"] = max(entry["files"], count)


if BACKUP.exists():
    for folder in sorted(BACKUP.iterdir()):
        if folder.is_dir():
            # ludusavi sanitizes ':' and '?' to '_' in folder names.
            add(folder, folder.name.replace("_", ":"))

for path, title in EXTRAS:
    if path.exists():
        add(path, title)

rows = []
for entry in sorted(entries.values(), key=lambda e: e["title"].lower()):
    rows.append(
        {
            "title": entry["title"],
            "first": entry["first"].isoformat(sep=" ", timespec="seconds"),
            "last": entry["last"].isoformat(sep=" ", timespec="seconds"),
            "files": entry["files"],
            "origins": entry["origins"],
        },
    )

OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"{len(rows)} games -> {OUT.resolve()}")
for row in rows:
    print(
        f"  {row['title'][:42]:44} {row['first'][:10]} .. "
        f"{row['last'][:10]}  files={row['files']}",
    )
