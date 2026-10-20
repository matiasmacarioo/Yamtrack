# Prompt: import my game play history from save files

Copy everything in the block below into a new agent session **on the gaming PC**
(the machine that has the games and saves installed), with this repo checked out
at `paths.repo` or backed up somewhere the agent can read.

---

```
Import my game play history into my self-hosted Yamtrack instance, using the
game save files on this PC as evidence of what I played and when.

Context:
- Yamtrack runs on my server as the Docker container "yamtrack", reachable at
  http://127.0.0.1:8010, and this repo has scripts/ + docs/ for this exact job:
    - scripts/build_save_history.py   (runs here, on the gaming PC)
    - scripts/import_save_history.py  (runs inside the container)
    - docs/importing-games-from-saves.md  (full guide, read it first)
- My Yamtrack username is <FILL IN>.
- Expected sources of save data on this PC:
    * a ludusavi backup folder (look for one in %USERPROFILE%, e.g.
      ludusavi-backup/) - preferred, it covers every launcher
    * %USERPROFILE%\Documents and %USERPROFILE%\Saved Games game folders
    * launcher installs: Steam, Epic, GOG Galaxy, Xbox app, Playnite, Hydra

Do this:
1. Read docs/importing-games-from-saves.md and scripts/README.md first.
2. Find where my saves actually live (list the candidate folders and report
   what you found and how many games each holds). If there is no ludusavi
   backup, say so and propose alternatives before doing anything.
3. Run: python scripts/build_save_history.py --out save_history.json
   Show me the resulting game list with the first/last save dates. Flag any
   titles that look like launcher folders, DLC, or engine folders rather than
   real games, and remove them.
4. Run the import in dry-run mode so I can check the IGDB matches:
   copy the manifest and script into the container, then
   docker exec -e YAMTRACK_USER=<my username> -e DRY_RUN=1 yamtrack python /tmp/import_save_history.py
   Report the matches and anything unmatched.
5. Only after I confirm, run it for real (drop DRY_RUN=1).
6. Fix obvious wrong matches by hand: IGDB often resolves long titles to the
   wrong entry (e.g. "Half-Life" -> "Half-Life 2"). Prefer correcting
   Item.title and Item.media_id over deleting and re-adding.
7. Verify in the app: the games list at /<username>/game, and that dates show
   up in /statistics and /journal. Delete nothing without asking me.

Rules:
- IGDB's free-text search frequently returns HTTP 429; retry with backoff
  rather than giving up, and never hammer it in a tight loop.
- Never modify or delete games I already track. Matches are by (media_id,
  source), so a re-run should only ever ADD.
- Do not commit or push anything; just leave the working tree clean.
- Re-running is safe: if this is a second run, skip games already imported.
```

---

Notes:

- Replace `<FILL IN>` with your Yamtrack username before sending.
- If the gaming PC is a different machine from the server, either run the
  container commands over SSH on the server, or just do step 3 here and step 4+
  on the server with the copied `save_history.json`.
- The scripts never delete or overwrite: they only create missing entries.
