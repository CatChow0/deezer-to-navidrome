# Stats tab: bring Wrapped, Maloja and lb-enricher into Deezer → Navidrome

## Context

Three containers do one job today. Navidrome sends plays to lb-enricher, which adds track length and album and forwards them to Maloja; Wrapped (`S:\Wrapped`) reads Maloja and shows charts and story recaps. The owner wants one app: a new **Stats** tab here, no lb-enricher, no Maloja, and stats that are correct.

Wrapped's bugs, all confirmed by reading the code and querying the live API:

| Symptom | Cause |
|---|---|
| Page can't load | `S:\Wrapped\ui\index.html` is binary garbage (`.bak` is fine) |
| No audio | Reads `trackId`, Maloja sends `track_id`; Maloja IDs aren't Navidrome IDs anyway |
| No genres | `/charts/genres` doesn't exist in Maloja 3.2.9; the error is swallowed |
| Everything "Nouveau" | Looks up `previous.top["artist"]`, the key is `artists` |
| Listening time too low | 41.3% of plays have no length and count as zero (562 h instead of about 1,120 h) |
| Wrong counts | "Unique artists" capped at 10; "new" compares two top-10 lists |
| Wrong covers | Search by name only, first result wins |
| Audio restarts every slide | Compares absolute `audio.src` with a relative URL |
| Charts never refresh | `lastKey` guard turns the 15 s refresh into a no-op |
| Month list skips months | `setMonth` overflow on the 29th–31st |

## What the data says (measured read-only, 2026-11-04)

| | Maloja | Navidrome | Merged |
|---|---|---|---|
| Plays | 18,773 | 22,294 rows, 21,804 after removing exact duplicates | **about 21,910** |
| With a track length | 58.7% | 100% | nearly all |

- Maloja recorded nothing on 26 days when Navidrome logged 2,647 plays, mostly 13 June to early July.
- 766 of Maloja's 913 title-mismatched plays share an exact timestamp with a Navidrome play: Maloja rewrote the title (`Love Galore` vs `Love Galore (feat. Travis Scott)`). Only **106** Maloja plays have no Navidrome play within 120 s. Why those are missing from Navidrome is unknown.
- Navidrome's artist field joins names with ` • `; its `participants` JSON has them separately. Its `genre` column is empty; genres are in the `tags` JSON (5,446 of 9,150 files), with junk such as `125` and `<unknown>`.
- Navidrome already holds a `ListenBrainzSessionKey` for the one user. One user only.

## Decisions

**The owner's**
- The app keeps its own history. One-time import merges Maloja and Navidrome; new plays come straight from Navidrome; both containers can then be removed.
- The import can be re-run from the app to reset or rebase the data.
- Start clean is refused while Navidrome's database isn't mounted: the button is disabled with a note saying why. When it is allowed, the confirmation shows how many plays would be lost.
- Stats opens on the latest recap, with older recap cards under it, then period charts.
- Keep all of Wrapped's stats, fixed. Add: filled genre gaps, listening habits, artist/album/track detail, and a searchable recent plays list.

**Claude's calls (can be overruled)**
- Rebuild has two modes, and both back up `stats.db` first (keep the last 3) and report what changed:
  - **Merge** (the default and the "rebase") only adds plays and refreshes metadata from the current sources and rules. It never deletes a play, so a file purged from Navidrome can't shrink the history. If a retag or a new key rule makes two tracks one, their plays are moved to the same track and same-play matching runs against stored plays, so nothing is counted twice.
  - **Start clean** wipes everything and uses only the sources. It's the only mode that can remove plays.
- Each play stores the album and length of what was actually played. 29 tracks appear on several albums (689 plays), and 15 have versions more than 10 s apart, so one album and length per track would misreport both.
- Genres are stored as tagged and grouped when displayed, through a small alias table in the code (for example `Rap`, `Hip Hop`, `Rap/Hip Hop` become one group; `Films/Games`, `Film Scores` and `Games` another). Regrouping later needs no re-import. Without this, the recap's genre slide would split your top genre across several rows.
- The first import keeps a copy of `malojadb.sqlite` in the data folder so a rebuild still works after Maloja is gone.
- Sources reach the app through read-only mounts, not browser upload.
- No Navidrome password: lengths come from the library index and Navidrome import, covers and audio from Deezer. Recap audio becomes 30-second previews instead of full tracks.
- English UI, matching the app.
- Tab order: Dashboard, Stats, Releases, Settings.
- The current month appears as a recap marked "so far". The hero card shows the latest *complete* month.
- Time = plays × track length. It is never presented as measured listening, and a coverage note shows when some lengths or genres are unknown.
- `S:\Wrapped`, `S:\lb-enricher` and `S:\Maloja` are not modified. Removing the containers is the owner's manual step.

**Not in this work:** editing or deleting individual plays, multiple users, sending plays on to other services, public share pages, full-track playback.

**Failure even if it technically works:** double-counted plays, a rebuild that silently loses history, a scrobble endpoint open to anyone, or numbers that disagree between the recap and the charts.

## Design

### Storage: `core/stats_db.py`
SQLite at `DATA_DIR/stats.db` (stdlib, WAL, one connection per call; gunicorn runs one worker with threads).

- `tracks`: `id`, `key` (unique), `title`, `artist_display`, `duration_sec` (fallback for plays with no length), `duration_source`, `genre` (raw), `genre_source`, `deezer_track_id`, `deezer_album_id`, `cover_url`, `lookup_at`
- `artists`, `track_artists`, `albums` (with album artist) for accurate per-artist and per-album counts
- `plays`: `id`, `track_id`, `album_id`, `duration_sec`, `listened_at` (UTC seconds), `source` (`navidrome`, `maloja`, `live`); unique on (`track_id`, `listened_at`); indexed on `listened_at`
- `meta`: schema version, last import report

**Track key:** artist + title, accent and case-insensitive. Drop `feat.` parts from the title (brackets or inline) and keep version markers (remix, live, etc.), so `Money Trees` and `Money Trees (feat. Jay Rock)` are one track and a remix stays separate. Check that `core/normalization.py:normalize_text` does this before reusing it; it may strip too much. For the artist part, use the *first* credited artist, since Maloja and Navidrome credit features differently.

### Import and rebuild: `core/stats_import.py`
Runs as a background task through `core/config.py:create_task` / `push_task_event`, so it appears in Activity.

1. Copy each source (`.db`, plus `-wal` and `-shm` if present) to a temp folder and read the copy. Opening a live WAL database in immutable mode misses recent plays.
2. Navidrome: read `scrobbles` joined to `media_file`, drop exact duplicates, split artists from `participants`, read genre from `tags` ignoring numeric and `<unknown>` values.
3. Maloja: read `scrobbles` joined to `tracks`, `trackartists`, `albums`.
4. **A Maloja play is the same play as a Navidrome play** if within 5 s (any title), or within 120 s with the same track key or a `rapidfuzz` title similarity of 85 or more (already a dependency). Navidrome's metadata wins. This rule is expected to leave 106–138 Maloja-only plays; list the 6–120 s cases in the real-data check to confirm they aren't retitled duplicates.
5. Fill missing lengths: Navidrome, then the library index, then Deezer lookup.
6. Write inside one transaction; a failed import changes nothing.

Running it twice must not change the totals. Check for the database schema and report a clear error if Navidrome's tables have changed.

### Receiving plays: `routes/listenbrainz.py`
- `POST /apis/listenbrainz/1/submit-listens`: same path as lb-enricher, so only the host changes. Ignore `playing_now`, require `listened_at`, split artists on ` • `. Answer 5xx on a database failure so Navidrome keeps the play in its retry buffer (lb-enricher always answered 200).
- `GET /apis/listenbrainz/1/validate-token`: needed when linking in Navidrome.
- **Auth:** public in `app.py:PUBLIC_ENDPOINTS`, but each route checks `Authorization: Token <scrobble token>` itself, including under `DISABLE_AUTH`. A separate token from the read-only API token, generated or pasted in Settings, or set with `SCROBBLE_TOKEN`.
- Metadata comes from the payload and the library index, never blocking on Deezer. Unknown fields are filled by the background job.

### Background lookups: `core/stats_enrich.py`
Called from `core/scheduler.py:_scheduler_loop` (30 s tick). Takes a small batch of tracks missing length, genre, cover or Deezer ID, most-played first. Reuse `core/deezer.py:search_deezer`, `_public_api`, `fetch_deezer_album_details`. Accept a match only under the strict rule from `pick_song` in the published `catchow/lb-enricher` image (`app/enrich.py`; the older copy in `S:\lb-enricher` doesn't have it): after removing accents and case, title and artist are each scored 1.0 if equal, 0.9 if one contains the other, else 0; the lower score must reach 0.9, or the track stays unknown. Add one guard: reject a match when only one side carries a version marker (remix, live, etc.). Failed lookups retry after a delay, not every tick.

Deezer preview URLs expire, so store the track ID and fetch the preview when needed, as `routes/search.py` already does.

### Queries and API: `core/stats_queries.py`, `routes/stats.py`
All totals come from SQL over `plays`, so recaps and charts share one code path and can't disagree. Period bounds use the browser's timezone (`Intl` → `tz` parameter), via `zoneinfo`; add `tzdata` to `requirements.txt` because `python:alpine` has no timezone data.

| Route | Returns |
|---|---|
| `GET /stats` | Page, via `routes/playlists.py:render_app("stats")` |
| `GET /api/stats/recaps` | Months and years with data, latest complete month |
| `GET /api/stats/overview?period&key&tz` | Totals, unique counts, top 10s, genres, habits, coverage |
| `GET /api/stats/recap?type&key&tz` | Recap data plus the previous period |
| `GET /api/stats/<artist\|album\|track>/<id>` | Plays over time, first and last listen, top tracks |
| `GET /api/stats/plays?q&page` | Searchable plays, newest first |
| `GET /api/stats/status` | Counts, last play received, token state, sources found, last import report |
| `POST /api/stats/import` | `{mode: merge\|clean}`; starts the task; one at a time |
| `POST`, `DELETE /api/stats/token` | Create or replace the scrobble token |

Rules behind the numbers:
- **New artist:** first-ever play falls within the period, across all history.
- **Comparison:** against the whole previous period, not its top 10.
- **First period:** history starts 16 Feb 2026, so "new" and comparison slides are hidden where there is no earlier data, and February is marked partial.
- **Genres:** real time per genre group, not an estimate. A track counts under its first genre only, so shares add up to 100%, with a "genres known for N% of plays" note.
- **Habits:** hour-by-weekday heatmap, busiest day, longest daily streak.

### Interface
Add to `templates/base.html` (nav link, stylesheet list), `templates/home.html` (view section), `static/js/views.js` (`TITLES`, `popstate` path check), `static/js/app.js`, plus the `.view-switch-pill` CSS, which must handle four tabs.

- `templates/_stats.html`, `static/css/stats.css`, `static/js/stats.js`: hero recap card, older recap cards, period picker, totals, top lists, genres, habits, recent plays. Load on first show through `onViewShown`, refresh when the view is shown again. No polling.
- `static/js/stats-story.js`: port slide builders and navigation from `S:\Wrapped\ui\app.js`, restyled with the app's tokens in `static/css/tokens.css` and its local fonts (no Google Fonts import). Slides: intro, genres, artist podium, track podium, new artists, discovery, habits, time comparison, outro. Keyboard, swipe and focus handling included.
- Audio: use the existing audio element in `static/js/player.js` through a new exported function, so volume and loudness settings are shared and only one thing plays. Hide the player bar during a story. A closing story stops playback.
- Detail views: reuse the existing drawer overlay (`static/js/overlay.js`).
- Empty state: if there are no plays, Stats explains the setup and links to Settings.
- Settings gets a "Listening stats" section in `templates/_settings.html`: token, the exact Navidrome setting to copy, sources found, last report, **Rebuild (merge)** and **Start clean**, with a confirmation showing current counts. The existing "Reset data" section leaves `stats.db` alone.

Use the `frontend-design` and `dataviz` skills when building the interface.

### Deployment and docs
`docker-compose.yml` gets commented read-only mounts and paths:

```yaml
# - /path/to/navidrome/data:/import/navidrome:ro
# - /path/to/Maloja:/import/maloja:ro
# STATS_NAVIDROME_DB: "/import/navidrome/navidrome.db"
# STATS_MALOJA_DB: "/import/maloja/malojadb.sqlite"
# SCROBBLE_TOKEN: ""
```

Update `README.md`, `DOCKERHUB_README.md`, `templates/_help.html` and `WHATS_NEW_ID`, and bump `VERSION` to 1.13.0 following the repo's `Minor - … - V1.13.0` commit style.

### Switching over (owner's steps, in Help and README)
1. Deploy, mount the two sources, run the import, check the numbers.
2. Set `ND_LISTENBRAINZ_BASEURL=http://deezer-to-navidrome:8080/apis/listenbrainz/1/` in Navidrome, restart it, and re-link ListenBrainz in its personal settings using the app's token.
3. Play a track and confirm it appears in Recent plays.
4. Run **Rebuild (merge)** to pick up plays made during the switch; Navidrome kept them in its own history.
5. Stop and remove lb-enricher, Maloja and Wrapped. Keep the read-only Navidrome mount: Start clean needs it, and Merge needs it to pick up new Navidrome plays.

## Verification

- **Unit tests** with stdlib `unittest` in a new `tests/` folder (`python -m unittest`; the repo has no tests today, and no new dependency is needed). Cover: track keys, same-play matching including retitled plays, import twice gives the same totals, Merge keeps app-only plays, Start clean removes them, failed import changes nothing, Start clean refused without Navidrome, Merge never deleting after a source shrinks, a retagged track not double-counted, per-play album and length, genre grouping, period and timezone bounds, new-artist and comparison rules, scrobble auth, `playing_now` ignored, duplicate submission counted once.
- **Real data:** import read-only copies of `S:\navidrome\data\navidrome.db` and `S:\Maloja\malojadb.sqlite` into a scratch `DATA_DIR`. Expect about 21,910–21,950 plays, 106–138 from Maloja only, at least 2,647 on the days Maloja missed, and nearly all with lengths. Spot-check October 2026 top artists against Maloja, allowing for its title and artist rewrites.
- **Real run:** start the app with the `run` skill. Send `curl` scrobbles with right and wrong tokens, including a Navidrome-shaped payload. Open Stats in a browser, play a recap to the end at desktop and phone widths, check audio, keyboard navigation and every section's empty state. Run both rebuild modes and check backups and reports.
- **Container:** build the image and confirm `/health` and timezones work on Alpine, as `Jenkinsfile`'s smoke test does.
- **Live Navidrome:** the owner points a real Navidrome at it and confirms linking and a real play. The Navidrome request format comes from memory and lb-enricher's code, so this is the one step that can't be proven from here.
