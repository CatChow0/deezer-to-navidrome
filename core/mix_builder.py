"""Builds the generated playlists. Daily Mix uses what you own, Daily Mix+ adds about
a third of tracks to download, Discover is only tracks you never heard. What they
download goes through the quarantine (core/trial.py).

The previous playlist stays in place until the new one is ready."""
import logging
import random
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import config, deezer_dl, mix_candidates, metadata_fix, mix_taste, mixes_db, stats_db, trial
from core.library import load_library_cache
from core.mix_taste import MIX_COUNT, MIX_SIZE

logger = logging.getLogger(__name__)

DAY = 86400
DAILY_EVERY = DAY
DISCOVER_EVERY = 7 * DAY
RECENT_DAYS = 3
BLEND_NEW_SHARE = 1 / 3
MIN_ANALYSED_SHARE = 0.9        # Automatic mixes wait for most of the tempo analysis.
DOWNLOAD_TIMEOUT = 600

DEFAULTS = {
    "daily": False,
    "blend": False,
    "discover": False,
    "daily_hours": 24,
    "discover_days": 7,
    "blend_new_per_run": 10,
    "discover_size": 30,
    "max_unheard": 100,
    "max_trial_gb": 20,
}
_run_lock = threading.Lock()


def load_settings(conn) -> dict:
    return {**DEFAULTS, **(mixes_db.get_meta(conn, "settings") or {})}


def save_settings(conn, changes) -> dict:
    settings = load_settings(conn)
    for key, value in changes.items():
        if key in ("daily", "blend", "discover"):
            settings[key] = bool(value)
        elif key in DEFAULTS:
            settings[key] = max(1, int(value))
    mixes_db.set_meta(conn, "settings", settings)
    return settings


def is_running() -> bool:
    return _run_lock.locked()


def library_entries() -> list:
    return load_library_cache(config.get_paths_from_config()[2])


def downloads_possible() -> str:
    """Why this install cannot download, or an empty string when it can."""
    if not deezer_dl.download_arl():
        return "Connect a Deezer account in Settings first."
    if not deezer_dl.download_dir_status().get("writable"):
        return "The downloads folder cannot be written to: check Settings."
    return ""


# --- Publishing ---------------------------------------------------------------

def _rows(tracks) -> list:
    """Preview rows of a generated playlist: every track already has its file."""
    from core.deezer import _row

    rows = []
    for position, track in enumerate(tracks, start=1):
        rows.append(_row(
            {"position": position, "track_id": track.get("deezer_id"), "artist": track["artist"],
             "title": track["title"], "album": track.get("album") or ""},
            {"path": track["path"], "tag_artist": track["artist"], "tag_title": track["title"]},
        ))
    return rows


def seed_cover(stats_conn, seed):
    """The picture the Stats tab already has for the track, album or artist."""
    from core.stats_covers import covers_dir

    row = stats_conn.execute("SELECT file FROM covers WHERE kind=? AND item_key=? AND file IS NOT NULL",
                             (seed.kind, seed.key)).fetchone()
    return covers_dir() / row["file"] if row else None


def _set_cover(playlist_id, cover) -> None:
    target = config.COVERS_DIR / f"{playlist_id}.jpg"
    if cover and Path(cover).exists():
        config.COVERS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cover, target)
    else:
        target.unlink(missing_ok=True)


def publish(playlist_id, title, subtitle, tracks, cover=None) -> None:
    """Saves the playlist and writes its .m3u8. The title never changes: Navidrome
    keeps one playlist per file, so a new name each day would pile them up."""
    from core.deezer import load_playlists, save_playlists, write_playlist_outputs

    rows = _rows(tracks)
    write_playlist_outputs(playlist_id, title, rows)
    _set_cover(playlist_id, cover)
    config.update_preview_state(playlist_id, {
        "playlist_id": playlist_id, "playlist_title": title, "rows": rows,
        "matched_count": len(rows), "unmatched_count": 0, "unchecked_count": 0,
    })
    playlists = [p for p in load_playlists() if p["id"] != playlist_id]
    save_playlists([*playlists, {"id": playlist_id, "title": title, "picture": "", "subtitle": subtitle}])


def unpublish(playlist_id) -> None:
    """Removes a generated playlist: only its own three files, then its folder."""
    from core.deezer import is_auto_id, load_playlists, playlist_title, save_playlists
    from core.utils import sanitize_filename

    if not is_auto_id(playlist_id):
        raise ValueError(f"Not a generated playlist: {playlist_id}")
    title = playlist_title(playlist_id)
    folder = config.get_paths_from_config()[1] / sanitize_filename(title)
    for name in (f"{sanitize_filename(title)}.m3u8", "report.json", "missing.txt"):
        (folder / name).unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    config.delete_playlist_cache(playlist_id)
    save_playlists([p for p in load_playlists() if p["id"] != playlist_id])


def _subtitle(seed) -> str:
    if seed.kind == "artist":
        return f"All about {seed.label}"
    return f"Around {seed.label}"


def _as_track(owned) -> dict:
    return {"artist": owned.artist, "title": owned.title, "album": owned.album, "path": owned.path}


# --- Downloads ----------------------------------------------------------------

def download_to_trial(conn, candidates, want, mix_id, now, enqueue=None) -> list:
    """Downloads until `want` tracks are saved, moving to the spares when one fails.
    Waits for each batch: a playlist must not point at a file not there yet."""
    if enqueue is None:
        from core.download_queue import enqueue_download as enqueue

    saved, queue = [], list(candidates)
    target = trial.trial_dir()
    target.mkdir(parents=True, exist_ok=True)
    while queue and len(saved) < want:
        batch, queue = queue[:want - len(saved)], queue[want - len(saved):]
        done, results = threading.Event(), {}
        left = [len(batch)]
        lock = threading.Lock()

        def finished(task, result, error, left=left, done=done, results=results, lock=lock):
            results[str(task.music_id)] = (result, error)
            with lock:
                left[0] -= 1
                if left[0] <= 0:
                    done.set()

        for candidate in batch:
            enqueue("track", candidate.deezer_id, on_done=finished, base_dir=str(target))
        if not done.wait(DOWNLOAD_TIMEOUT):
            logger.warning("Downloads for %s took too long", mix_id)
        for candidate in batch:
            result, error = results.get(candidate.deezer_id, (None, "No answer"))
            if error or not result or not result.get("path"):
                logger.info("Could not download %s: %s", candidate.deezer_id, error)
                continue
            trial.add_download(conn, candidate.deezer_id, candidate.artist, candidate.title, candidate.album,
                               result["path"], mix_id, now)
            row = trial.get(conn, candidate.deezer_id)
            # A track already decided on (it was on disk) does not join the mix.
            if row["state"] == trial.ON_TRIAL:
                saved.append({"deezer_id": candidate.deezer_id, "artist": candidate.artist, "title": candidate.title,
                              "album": candidate.album, "path": result["path"]})
    return saved


def _trial_track(row) -> dict:
    return {"deezer_id": row["deezer_id"], "artist": row["artist"], "title": row["title"],
            "album": row["album"], "path": row["path"]}


# --- Generation ---------------------------------------------------------------

class _Run:
    def __init__(self, conn, stats_conn, now, seed_text):
        self.conn, self.stats = conn, stats_conn
        self.now = now
        self.rng = random.Random(seed_text)
        self.settings = load_settings(conn)
        self.taste = mix_taste.build_taste(stats_conn, now)
        self.seeds = mix_taste.find_seeds(stats_conn, now)
        self.owned = mix_taste.owned_tracks(
            [e for e in library_entries() if e.get("path") and Path(e["path"]).exists()],
            exclude_under=[str(trial.trial_dir())],
            features=metadata_fix.features_map(conn),
        )
        self.notes = []
        self.downloaded = 0
        self.emit = lambda message: None
        self.ids = mix_candidates.artist_ids(stats_conn)

    def exclusions(self, **kw):
        known = {r["deezer_id"] for r in self.conn.execute("SELECT deezer_id FROM trial_tracks")}
        return mix_candidates.Exclusions(self.owned, known_ids=known, rejected_keys=trial.rejected(self.conn)["keys"], **kw)

    def download_room(self, wanted) -> int:
        """How many tracks may be fetched now. A limit reached is said, not silent."""
        used = trial.usage(self.conn, trial.plays_since_download(self.conn, self.stats))
        if used["bytes"] >= self.settings["max_trial_gb"] * 1024 ** 3:
            self.notes.append(f"Quarantine limit of {self.settings['max_trial_gb']} GB reached: nothing new was downloaded.")
            return 0
        room = self.settings["max_unheard"] - used["unheard"]
        if room <= 0:
            self.notes.append(f"{used['unheard']} tracks on trial are still unheard: nothing new was downloaded.")
            return 0
        return min(wanted, room)

    def seed_tempos(self, seed):
        by_key = {t.key: t for t in self.owned}
        return [(by_key[k].bpm, w) for k, w in seed.tracks.items() if k in by_key and by_key[k].bpm]

    def choose(self, name):
        recent = set(mixes_db.get_meta(self.conn, f"seeds_{name}", []))
        other = set(mixes_db.get_meta(self.conn, "seeds_today", []))
        chosen = mix_taste.choose_seeds(self.seeds, recent_ids=recent | other, rng=self.rng, count=MIX_COUNT)
        mixes_db.set_meta(self.conn, f"seeds_{name}", [s.id for s in chosen])
        mixes_db.set_meta(self.conn, "seeds_today", sorted(other | {s.id for s in chosen}))
        return chosen

    def recent(self, name):
        return mixes_db.recent_keys(self.conn, f"auto-{name}", self.now - RECENT_DAYS * DAY)

    def remember(self, name, keys):
        mixes_db.remember(self.conn, f"auto-{name}", keys, self.now)


def build_daily(run) -> list:
    built = []
    recent = run.recent("daily")
    for slot, seed in enumerate(run.choose("daily"), start=1):
        run.emit(f"Daily Mix {slot}: {seed.label}")
        picks = mix_taste.pick_for_seed(run.taste, seed, run.owned, recent=recent, rng=run.rng)
        if not picks:
            continue
        publish(f"auto-daily-{len(built) + 1}", f"Daily Mix {len(built) + 1}", _subtitle(seed), [_as_track(p) for p in picks],
                cover=seed_cover(run.stats, seed))
        run.remember("daily", [p.key for p in picks])
        built.append(f"auto-daily-{len(built) + 1}")
    return built


def build_blend(run) -> list:
    """Your tracks, then tracks on trial you have not heard yet, then new ones: a
    track gets its chance before more are fetched. The new ones for the run are
    shared between the mixes."""
    built = []
    recent = run.recent("blend")
    plays = trial.plays_since_download(run.conn, run.stats)
    unheard = [r for r in trial.active(run.conn) if r["state"] == trial.ON_TRIAL and not plays.get(r["deezer_id"])]
    run.rng.shuffle(unheard)
    seeds = run.choose("blend")
    budget = run.download_room(run.settings["blend_new_per_run"])
    new_slots = round(MIX_SIZE * BLEND_NEW_SHARE)
    for index, seed in enumerate(seeds):
        # Between mixes: every file already downloaded has been registered on trial.
        run.emit(f"Daily Mix+ {index + 1}: {seed.label}")
        picks = mix_taste.pick_for_seed(run.taste, seed, run.owned, recent=recent, size=MIX_SIZE - new_slots, rng=run.rng)
        if not picks:
            continue
        slot = f"auto-blend-{len(built) + 1}"
        trial_tracks = [_trial_track(row) for row in unheard[:new_slots]]
        unheard = unheard[new_slots:]
        share = min(budget // max(1, len(seeds) - index), new_slots - len(trial_tracks))
        new_tracks = []
        if share > 0:
            pool = mix_candidates.seed_pool(run.conn, seed, run.ids, run.now)
            per_artist = share if seed.kind == "artist" else mix_taste.PER_ARTIST
            chosen = mix_candidates.select(pool, run.exclusions(), share, per_artist, run.rng, run.seed_tempos(seed))
            new_tracks = download_to_trial(run.conn, chosen, share, slot, run.now)
            budget -= len(new_tracks)
            run.downloaded += len(new_tracks)
        tracks = [_as_track(p) for p in picks] + trial_tracks + new_tracks
        run.rng.shuffle(tracks)
        publish(slot, f"Daily Mix+ {len(built) + 1}", _subtitle(seed), tracks, cover=seed_cover(run.stats, seed))
        run.remember("blend", [p.key for p in picks])
        built.append(slot)
    return built


def build_discover(run) -> list:
    """Only what you never heard, around your habits: new releases from the artists
    you follow, and tracks of the artists closest to your favorites."""
    from core.releases import load_releases

    size = run.download_room(run.settings["discover_size"])
    if size <= 0:
        return []
    today = datetime.fromtimestamp(run.now, tz=timezone.utc).date()
    since = (today - timedelta(days=mix_candidates.RELEASES_WINDOW_DAYS)).isoformat()
    rules = run.exclusions(played=run.taste.track_plays, never_played_only=True)
    new_share = round(size * mix_candidates.DISCOVER_RELEASE_SHARE)
    newest = mix_candidates.select(mix_candidates.release_pool(load_releases().get("releases", []), since),
                                   rules, new_share, mix_taste.PER_ARTIST, run.rng)
    around = mix_candidates.select(mix_candidates.habit_pool(run.conn, run.taste, run.ids, run.now),
                                   rules, size, mix_taste.PER_ARTIST, run.rng)
    taken, chosen = set(), []
    for candidate in [*newest, *around]:
        if candidate.base not in taken:
            taken.add(candidate.base)
            chosen.append(candidate)
    tracks = download_to_trial(run.conn, chosen, size, "auto-discover", run.now)
    run.downloaded += len(tracks)
    if not tracks:
        return []
    run.rng.shuffle(tracks)
    publish("auto-discover", "Discover", "Only tracks you never heard", tracks)
    return ["auto-discover"]


def publish_trial_playlist(conn) -> bool:
    """Every track in quarantine, so one that left today's mix can still be heard."""
    rows = [r for r in trial.active(conn) if Path(r["path"]).exists()]
    if not rows:
        if config.get_preview_state("auto-trial"):
            unpublish("auto-trial")
        return False
    publish("auto-trial", "On trial", f"{len(rows)} tracks waiting for a verdict", [_trial_track(r) for r in rows])
    return True


def review_trial(conn, stats_conn, now) -> dict:
    """The daily verdicts, then the trash."""
    outside = mix_taste.owned_tracks(library_entries(), exclude_under=[str(trial.trial_dir())])
    marks = trial.navidrome_marks(conn)
    report = trial.evaluate(conn, trial.plays_since_download(conn, stats_conn), marks or {},
                            trial.paths_in_regular_playlists(), {t.key for t in outside}, now)
    report["purged"] = trial.purge(conn, now)
    report["navidrome_marks"] = marks is not None
    return report


def _refresh_library(progress) -> None:
    from core.library import refresh_library_cache_incremental_with_progress

    refresh_library_cache_incremental_with_progress(progress_cb=lambda **kw: None)


def generate(versions=None, progress=None, now=None) -> dict:
    """One run. `versions`: what to build, by default what is turned on."""
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("Your mixes are already being generated")
    emit = progress or (lambda message: None)
    now = int(now or time.time())
    conn, stats_conn = mixes_db.connect(), stats_db.connect()
    try:
        settings = load_settings(conn)
        wanted = versions if versions is not None else [v for v in ("daily", "blend", "discover") if settings[v]]
        mixes_db.set_meta(conn, "seeds_today", [])
        emit("Checking the tracks on trial")
        report = review_trial(conn, stats_conn, now)
        run = _Run(conn, stats_conn, now, f"{now // DAY}")
        run.emit = emit
        built = {}
        blocked = downloads_possible()
        for name, build, downloads in (("daily", build_daily, False), ("blend", build_blend, True),
                                       ("discover", build_discover, True)):
            if name not in wanted:
                continue
            if downloads and blocked:
                run.notes.append(f"{name}: {blocked}")
                continue
            emit(f"Building {name}")
            built[name] = build(run)
            mixes_db.set_meta(conn, f"last_{name}", now)
            _drop_stale(name, built[name])
        if run.downloaded:
            emit("Refreshing the library")
            _refresh_library(emit)
        publish_trial_playlist(conn)
        result = {"built": built, "notes": run.notes, "trial": report, "downloaded": run.downloaded}
        mixes_db.set_meta(conn, "last_run", {"at": now, "notes": run.notes})
        return result
    finally:
        conn.close()
        stats_conn.close()
        _run_lock.release()


def _drop_stale(name, kept) -> None:
    """A mix that could not be built today leaves, rather than stay out of date."""
    from core.deezer import load_playlists

    prefix = "auto-discover" if name == "discover" else f"auto-{name}-"
    if name == "discover" and not kept:
        return  # Nothing new this week: last week's still has tracks to hear.
    for playlist in load_playlists():
        if playlist["id"].startswith(prefix) and playlist["id"] not in kept:
            unpublish(playlist["id"])


def set_enabled(conn, name, enabled) -> None:
    """Turning a version off removes its playlists. Files on trial stay on trial."""
    from core.deezer import load_playlists

    save_settings(conn, {name: enabled})
    if not enabled:
        prefix = "auto-discover" if name == "discover" else f"auto-{name}-"
        for playlist in load_playlists():
            if playlist["id"].startswith(prefix):
                unpublish(playlist["id"])


def due_versions(conn, now) -> list:
    settings = load_settings(conn)
    due = []
    if settings["daily"] and now - mixes_db.get_meta(conn, "last_daily", 0) >= settings["daily_hours"] * 3600:
        due.append("daily")
    if settings["blend"] and now - mixes_db.get_meta(conn, "last_blend", 0) >= settings["daily_hours"] * 3600:
        due.append("blend")
    if settings["discover"] and now - mixes_db.get_meta(conn, "last_discover", 0) >= settings["discover_days"] * DAY:
        due.append("discover")
    return due


def tick(now=None) -> None:
    """Called by the scheduler: keeps the tempo analysis going, and starts what is
    due once most of the library has been measured, or the mixes would ignore tempo."""
    if is_running():
        return
    now = int(now or time.time())
    conn = mixes_db.connect()
    try:
        settings = load_settings(conn)
        mixes_on = any(settings[v] for v in ("daily", "blend", "discover"))
        # Files are only tagged once you asked for it: the button, or turning on a mix.
        if not mixes_on and not mixes_db.get_meta(conn, "metadata_fix_on"):
            return
        entries = library_entries()
        state = metadata_fix.status(conn, entries)
        # Cancelled by hand: it stays stopped until you ask for it again.
        if state["left"] and not metadata_fix.paused(conn):
            metadata_fix.start_background(library_entries)
        if not mixes_on:
            return
        analysed = 1 - state["left"] / state["total"] if state["total"] else 1
        due = due_versions(conn, now) if analysed >= MIN_ANALYSED_SHARE else []
    finally:
        conn.close()
    if due:
        start_task(due)


def start_task(versions, title="Generating your mixes"):
    """In the background, followed in Activity."""
    from core.config import create_task, push_task_event

    task_id = create_task(title, kind="mixes", cancellable=True)

    def runner():
        try:
            result = generate(versions, progress=lambda m: push_task_event(task_id, m, stage="build"))
            count = sum(len(v) for v in result["built"].values())
            summary = f"{count} playlists ready, {result['downloaded']} tracks downloaded"
            if result["notes"]:
                summary += ". " + " ".join(result["notes"])
            push_task_event(task_id, summary, stage="done", progress=100, done=True)
        except config.TaskCancelled:
            # Its turn counts as taken, or the next check would start it again at once.
            conn = mixes_db.connect()
            try:
                for name in versions:
                    mixes_db.set_meta(conn, f"last_{name}", int(time.time()))
            finally:
                conn.close()
            config.finish_cancelled(task_id, "Cancelled: the playlists already built stay. The next refresh runs as planned")
        except Exception as e:
            logger.error("Could not generate the mixes: %s", e)
            push_task_event(task_id, f"Could not generate the mixes: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True, name="mix-builder").start()
    return task_id
