# Importing your play history from game saves and launchers

Yamtrack's only built-in games importer is **Steam** (`STEAM_API_KEY`, see
`docs/env-variables.md`). Steam's API returns owned AppIDs plus playtime, which
misses everything you played outside Steam, and everything Steam doesn't track
(non-Steam shortcuts, Epic, GOG, Xbox app, VR mods, emulators, ...).

Save files fill that gap: they exist for nearly every game, live in
well-known folders, and their **file modification times** are a genuine record
of when you last played. This guide covers the sources and how to turn them
into Yamtrack entries.

## Where saves live

| Source | Path | Notes |
|---|---|---|
| **ludusavi backup** | `%USERPROFILE%\<backup-folder>` | Best single source. Backs up saves for every detected game across Steam/Epic/GOG/Xbox/emulators. Mod times and original paths are preserved; only its own `mapping.yaml` is stamped with the backup date. |
| Steam userdata | `C:\Program Files (x86)\Steam\userdata\<steam3id>\<appid>\` | Per-account; contains Steam Cloud state. |
| Steam library | `<library>\steamapps\common\<game>\` | Install time only — not play time. Avoid. |
| Documents | `%USERPROFILE%\Documents\<game or publisher>\` | e.g. `My Games\`, `Rockstar Games\`, `KoeiTecmo\`, `CD Projekt Red\`. |
| Saved Games | `%USERPROFILE%\Saved Games\<game>\` | Used by many Microsoft Store / Xbox games. |
| AppData | `%LOCALAPPDATA%\<game>`, `%APPDATA%\<game>`, `%LOCALAPPDATA%Low\<game>` | Small settings files; still carries a "last launched" date. |

Launcher installs are also a decent inventory (which games you own) even when
playtime isn't stored locally: Playnite (`%APPDATA%\Playnite`), Epic
(`%LOCALAPPDATA%\EpicGamesLauncher`), GOG Galaxy (`C:\ProgramData\GOG.com`),
Xbox app (`...\Packages\Microsoft.GamingApp_...`), Hydra, and
`HKCU\Software\Valve\Steam\Apps` for Steam titles.

## How this was done here

1. Scan the backup + curated game folders, keeping the earliest and latest save
   file per title — that pair is the play window. Ignore tool-generated files
   (`mapping.yaml`).
2. Resolve each title to an IGDB id and create a `Game` row:
   - `start_date` = earliest save, `end_date` = latest save
   - `progress` left at 0 (save files don't carry playtime)
   - status = `In progress` if the last save is within ~90 days, else `Paused`
   - `_history_date` = last save, so the journal/heatmap shows the real dates
3. Write with `bulk_create_media` from `integrations.imports.helpers`, which
   mirrors what the built-in importers do (same history behaviour). Rows are
   matched by `(media_id, source)`, so re-running only adds what's missing and
   never overwrites existing data.

Both scripts live in `scripts/` in this repo. There is also a ready-made agent
prompt at `docs/prompt-import-games-from-saves.md` you can paste into a session
on the gaming PC to run the whole flow.

## Caveats

- **IGDB 429**: the free-text `search` command (what the app's game search and
  the built-in importers use) can return `429 Too Many Requests` — an
  account/IP throttle, not a client bug. The `where name ~ *"..."*` filter path
  usually still works, which is a useful fallback for one-off lookups.
- Wrong or missing matches are normal for long titles (`Half-Life` matched
  `Half-Life 2`; `Ghost of Tsushima: Director's Cut` has no plain-name entry).
  Correct `Item.title` / `Item.media_id` afterwards if it matters.
- Saves date a *session*, not a purchase — a game you own but never launched
  won't appear, and one you played before a clean install may start later than
  you actually did.
- Backups are snapshots: re-scan periodically to refresh the latest-save date.

## Playing games on other systems

For anything not on the PC (console, Switch, cloud), use the
**HowLongToBeat** importer (`Import > HowLongToBeat`). It accepts the CSV shape
used by the Playnite HLTB plugin: `Title`, `Platform`, status columns marked
with `X` (`Playing`/`Backlog`/`Replay`/`Completed`/`Retired`), `Start Date`,
`Completion Date`, times as `H:MM:SS`, `Review` as 0-100, `Updated`. The
HowLongToBeat website's own export is close but not identical — convert it
before uploading.
