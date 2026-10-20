# Save-file play-history scripts

Yamtrack's only built-in games importer is Steam. These two scripts recover the
play history for everything else, using game **save files** as evidence: the
oldest and newest save file for a title become its play window.

See `docs/importing-games-from-saves.md` for the full guide (where saves live,
caveats, IGDB throttling, and the HowLongToBeat path for console games).

## 1. Build the manifest (on the gaming PC)

```powershell
python scripts/build_save_history.py --out save_history.json
```

Scans your ludusavi backup (`%USERPROFILE%\ludusavi-backup` by default, override
with `--backup DIR`) plus curated game folders under `Documents` / `Saved Games`,
and writes one entry per game:

```json
{ "title": "Cyberpunk 2077", "first": "2025-06-29 19:00:39", "last": "2025-09-17 21:14:02", "files": 126 }
```

Add any game the scan misses to the `EXTRAS` list at the top of the script.

## 2. Import into Yamtrack (on the server)

```bash
docker cp save_history.json yamtrack:/tmp/pc_games.json
docker cp scripts/import_save_history.py yamtrack:/tmp/
docker exec -e YAMTRACK_USER=matias yamtrack python /tmp/import_save_history.py
```

Preview first with `-e DRY_RUN=1` to see the IGDB matches without writing.

Each game becomes a `Game` row: `start_date` = first save, `end_date` = last
save, `progress` = 0 (saves don't record playtime), status `In progress` if the
last save is within `RECENT_DAYS` (default 90) else `Paused`, plus a dated
history entry so the journal shows the real dates.

Rows are matched by `(media_id, source)` and existing games are never modified,
so **re-running is safe** — it only adds what's missing.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `YAMTRACK_USER` | — | username to import for (required) |
| `YAMTRACK_DATA` | `/tmp/pc_games.json` | manifest path |
| `RECENT_DAYS` | `90` | last save within N days counts as "In progress" |
| `DRY_RUN` | — | `1` = resolve and report only, write nothing |

## Notes

- IGDB's free-text search can return `429 Too Many Requests`; the importer
  retries with backoff. If a title still fails, search for it in the app and
  add it by hand.
- Long titles sometimes match the wrong IGDB entry (`Half-Life` -> `Half-Life 2`).
  Fix `Item.title` / `Item.media_id` afterwards if it matters.
- Some titles never resolve through the app's search command even when they
  exist in IGDB (storefront-flavoured names like `Hitman: World of
  Assassination`, `Resident Evil 2 (2019)`, `Skyrim VR`). They tagged fine
  through the `where name ~ *"..."*` filter instead, which is what the
  hand-fixup pass uses. Expect a handful of these per run.
