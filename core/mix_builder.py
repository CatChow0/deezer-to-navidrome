"""Builds the generated playlists. Daily Mix uses what you own, Daily Mix+ adds a chosen
share of tracks to download, Discover is only tracks you never heard. What they
download goes through the quarantine (core/trial.py). One mode is on at a time: off,
Daily Mix or Daily Mix+. Discover has its own switch.

Each Navidrome account has its own: its settings, its mixes built from its own
listening history (and Discover from its Deezer account's releases), published
for it alone, and its quarantine. The disk limits are the same for everyone,
as the disk is. One account is built at a time: they share the Deezer quota.

The previous playlist stays in place until the new one is ready."""
import logging
import random
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import account_context, config, deezer_dl, mix_candidates, metadata_fix, mix_taste, mixes_db, stats_db, trial
from core.library import load_library_cache
from core.mix_taste import MIN_MIX_SIZE, MIX_COUNT, MIX_SIZE

logger = logging.getLogger(__name__)

DAY = 86400
DAILY_EVERY = DAY
DISCOVER_EVERY = 7 * DAY
RECENT_DAYS = 3
MIN_ANALYSED_SHARE = 0.9        # Automatic mixes wait for most of the tempo analysis.
DOWNLOAD_TIMEOUT = 600

MIX_MODES = ("off", "daily", "blend")
DEFAULTS = {
    "mix_mode": "off",
    "discover": False,
    "daily_hours": 24,
    "discover_days": 7,
    "mix_size": MIX_SIZE,
    "discover_size": 30,
    "blend_new_percent": 33,
    "max_unheard": 100,
    "max_trial_gb": 20,
    "trial_auto": True,
    "trial_days": trial.TRIAL_DAYS,
    "trash_days": trial.TRASH_DAYS,
    "trial_delete": False,
    "trial_bypass": False,
    "trial_plays": trial.KEEP_PLAYS,
    "trial_marks": True,
}
BOUNDS = {"mix_size": (MIN_MIX_SIZE, 100), "blend_new_percent": (1, 90), "trial_days": (1, 365),
          "trash_days": (1, 365), "trial_plays": (1, 50)}
SWITCHES = {"discover", "trial_auto", "trial_delete", "trial_bypass", "trial_marks"}
# One disk for every profile: the same limits for all.
SHARED = {"max_unheard", "max_trial_gb"}
# What each profile keeps in mixes.db's meta table, under its own keys.
PER_PROFILE_KEYS = ("settings", "last_run", "seeds_today", "seeds_daily", "seeds_blend", "last_daily", "last_blend",
                    "last_discover", "trial_rules_v2")
TRIAL_KEYS = {"trial_auto", "trial_days", "trash_days", "trial_delete", "trial_bypass", "trial_plays", "trial_marks"}
_run_lock = threading.Lock()
_review_lock = threading.Lock()


def key(account, name) -> str:
    """Where one profile's state is kept in mixes.db's meta table. The install's
    account keeps the names it always had; the others' carry their ID."""
    account = stats_db.checked_account(account)
    return name if account == stats_db.FIRST_ACCOUNT else f"{account}:{name}"


def _shared_settings(conn) -> dict:
    saved = mixes_db.get_meta(conn, "shared_settings")
    if saved is None:
        # Before profiles, the limits were saved with the install's settings.
        saved = mixes_db.get_meta(conn, "settings") or {}
    return {k: saved[k] for k in SHARED if k in saved}


def load_settings(conn, account) -> dict:
    saved = mixes_db.get_meta(conn, key(account, "settings")) or {}
    settings = {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS and k not in SHARED}, **_shared_settings(conn)}
    if "mix_mode" not in saved:
        # Saved when Daily Mix and Daily Mix+ were two separate switches.
        settings["mix_mode"] = "blend" if saved.get("blend") else "daily" if saved.get("daily") else "off"
    return settings


def save_settings(conn, account, changes) -> dict:
    settings = load_settings(conn, account)
    for name, value in changes.items():
        if name == "mix_mode":
            if value not in MIX_MODES:
                raise ValueError(f"Unknown mode: {value}")
            settings[name] = value
        elif name in SWITCHES:
            settings[name] = bool(value)
        elif name in DEFAULTS:
            low, high = BOUNDS.get(name, (1, None))
            number = max(low, int(value))
            settings[name] = min(high, number) if high else number
    mixes_db.set_meta(conn, key(account, "settings"), {k: v for k, v in settings.items() if k not in SHARED})
    mixes_db.set_meta(conn, "shared_settings", {k: settings[k] for k in SHARED})
    return settings


def last_run(conn, account):
    return mixes_db.get_meta(conn, key(account, "last_run"))


def accounts() -> list:
    """Every profile, in the order of Settings."""
    from core import nd_accounts

    try:
        found = [a["id"] for a in nd_accounts.list_accounts()]
    except Exception:
        found = []
    return found or [stats_db.FIRST_ACCOUNT]


def enabled_versions(settings) -> list:
    """What runs, in build order."""
    return ([settings["mix_mode"]] if settings["mix_mode"] != "off" else []) + (["discover"] if settings["discover"] else [])


def is_running() -> bool:
    return _run_lock.locked()


def library_entries() -> list:
    return load_library_cache(config.get_paths_from_config()[2])


def library_copies() -> dict:
    """track key -> its file in the library, outside the quarantine."""
    return {t.key: t.path for t in mix_taste.owned_tracks(library_entries(), exclude_under=[str(trial.trial_dir())])}


def downloads_possible() -> str:
    """Why this install cannot download, or an empty string when it can."""
    if not deezer_dl.download_arl():
        return "Add a Deezer account in Settings → Deezer accounts first."
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


def publish(account, playlist_id, title, subtitle, tracks, cover=None) -> None:
    """Saves the playlist, for this account alone, and puts it in its Navidrome
    (core/publish.py). The title never changes: Navidrome keeps one playlist per
    file, so a new name each day would pile them up."""
    from core import publish as navidrome
    from core.deezer import load_playlists, save_playlists

    rows = _rows(tracks)
    playlists = [p for p in load_playlists() if p["id"] != playlist_id]
    save_playlists([*playlists, {"id": playlist_id, "title": title, "picture": "", "subtitle": subtitle,
                                 "accounts": [account]}])
    navidrome.publish(playlist_id, title, rows)
    _set_cover(playlist_id, cover)
    config.update_preview_state(playlist_id, {
        "playlist_id": playlist_id, "playlist_title": title, "rows": rows,
        "matched_count": len(rows), "unmatched_count": 0, "unchecked_count": 0,
    })


def unpublish(playlist_id) -> None:
    """Removes a generated playlist from its account, in Navidrome too: the
    account that uses files loses only its own three files, then their folder;
    for the others, nothing is deleted by name, since another profile's mix has
    the same title."""
    from core import publish as navidrome
    from core.deezer import accounts_for, is_auto_id, load_playlists, playlist_title, save_playlists

    if not is_auto_id(playlist_id):
        raise ValueError(f"Not a generated playlist: {playlist_id}")
    title = playlist_title(playlist_id)
    navidrome.remove_from(playlist_id, title, accounts_for(playlist_id))
    navidrome.unpublish(playlist_id)
    config.delete_playlist_cache(playlist_id)
    save_playlists([p for p in load_playlists() if p["id"] != playlist_id])


def _subtitle(seed) -> str:
    if seed.kind == "artist":
        return f"All about {seed.label}"
    return f"Around {seed.label}"


def _as_track(owned) -> dict:
    return {"artist": owned.artist, "title": owned.title, "album": owned.album, "path": owned.path}


# --- Downloads ----------------------------------------------------------------

def download_to_trial(conn, account, candidates, want, mix_id, now, enqueue=None) -> list:
    """Downloads until `want` tracks are saved, moving to the spares when one fails,
    into this account's quarantine. A track another profile already has on trial
    (or in its trash) is shared, not downloaded again. Waits for each batch: a
    playlist must not point at a file not there yet."""
    if enqueue is None:
        from core.download_queue import enqueue_download as enqueue

    saved, queue = [], list(candidates)
    target = trial.trial_dir()
    target.mkdir(parents=True, exist_ok=True)
    while queue and len(saved) < want:
        batch = []
        while queue and len(saved) + len(batch) < want:
            candidate = queue.pop(0)
            if trial.share(conn, account, candidate.deezer_id, mix_id, now):
                row = trial.get(conn, candidate.deezer_id, account)
                saved.append({"deezer_id": candidate.deezer_id, "artist": row["artist"], "title": row["title"],
                              "album": row["album"], "path": row["path"]})
            else:
                batch.append(candidate)
        if not batch:
            continue
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
            trial.add_download(conn, account, candidate.deezer_id, candidate.artist, candidate.title, candidate.album,
                               result["path"], mix_id, now)
            row = trial.get(conn, candidate.deezer_id, account)
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
    def __init__(self, conn, stats_conn, account, now, seed_text):
        self.conn, self.stats = conn, stats_conn
        self.account = account
        self.now = now
        self.rng = random.Random(seed_text)
        self.settings = load_settings(conn, account)
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
        # Not proposed again: what this profile already had in its quarantine, and
        # what anyone kept, now in the library. A track on trial for another
        # profile may be proposed: its file is shared, not downloaded again.
        known = {r["deezer_id"] for r in self.conn.execute(
            "SELECT deezer_id FROM trial_tracks WHERE account_id=? OR state=?", (self.account, trial.KEPT))}
        return mix_candidates.Exclusions(self.owned, known_ids=known,
                                         rejected_keys=trial.rejected(self.conn, self.account)["keys"], **kw)

    def download_room(self, wanted) -> int:
        """How many tracks may be fetched now, by the limits every profile shares.
        A limit reached is said, not silent."""
        used = trial.usage(self.conn, trial.plays_of_everyone(self.conn))
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
        recent = set(mixes_db.get_meta(self.conn, key(self.account, f"seeds_{name}"), []))
        other = set(mixes_db.get_meta(self.conn, key(self.account, "seeds_today"), []))
        chosen = mix_taste.choose_seeds(self.seeds, recent_ids=recent | other, rng=self.rng, count=MIX_COUNT)
        mixes_db.set_meta(self.conn, key(self.account, f"seeds_{name}"), [s.id for s in chosen])
        mixes_db.set_meta(self.conn, key(self.account, "seeds_today"), sorted(other | {s.id for s in chosen}))
        return chosen

    def playlist_id(self, name, slot=None):
        from core.deezer import auto_id

        return auto_id(self.account, name, slot)

    def recent(self, name):
        return mixes_db.recent_keys(self.conn, self.playlist_id(name), self.now - RECENT_DAYS * DAY)

    def remember(self, name, keys):
        mixes_db.remember(self.conn, self.playlist_id(name), keys, self.now)


def build_daily(run) -> list:
    built = []
    recent = run.recent("daily")
    for slot, seed in enumerate(run.choose("daily"), start=1):
        run.emit(f"Daily Mix {slot}: {seed.label}")
        picks = mix_taste.pick_for_seed(run.taste, seed, run.owned, recent=recent, size=run.settings["mix_size"], rng=run.rng)
        if not picks:
            continue
        slot = run.playlist_id("daily", len(built) + 1)
        publish(run.account, slot, f"Daily Mix {len(built) + 1}", _subtitle(seed), [_as_track(p) for p in picks],
                cover=seed_cover(run.stats, seed))
        run.remember("daily", [p.key for p in picks])
        built.append(slot)
    return built


def build_blend(run) -> list:
    """Your tracks, then tracks on trial you have not heard yet, then new ones: a
    track gets its chance before more are fetched. What the disk limits allow is
    shared between the mixes."""
    built = []
    recent = run.recent("blend")
    plays = trial.plays_since_download(run.conn, run.stats, run.account)
    unheard = [r for r in trial.active(run.conn, run.account) if r["state"] == trial.ON_TRIAL and not plays.get(r["deezer_id"])]
    run.rng.shuffle(unheard)
    seeds = run.choose("blend")
    size, share_new = run.settings["mix_size"], run.settings["blend_new_percent"] / 100
    new_slots = max(1, round(size * share_new))
    budget = run.download_room(new_slots * len(seeds))
    # Your own tracks are only part of this mix: the bar for "worth a playlist" follows.
    minimum = max(1, round(MIN_MIX_SIZE * (1 - share_new)))
    for index, seed in enumerate(seeds):
        # Between mixes: every file already downloaded has been registered on trial.
        run.emit(f"Daily Mix+ {index + 1}: {seed.label}")
        ranked = mix_taste.pick_for_seed(run.taste, seed, run.owned, recent=recent, size=size, rng=run.rng, minimum=minimum)
        if not ranked:
            continue
        picks, spare = ranked[:size - new_slots], ranked[size - new_slots:]
        slot = run.playlist_id("blend", len(built) + 1)
        trial_tracks = [_trial_track(row) for row in unheard[:new_slots]]
        unheard = unheard[new_slots:]
        share = min(budget // max(1, len(seeds) - index), new_slots - len(trial_tracks))
        new_tracks = []
        if share > 0:
            pool = mix_candidates.seed_pool(run.conn, seed, run.ids, run.now)
            per_artist = share if seed.kind == "artist" else mix_taste.PER_ARTIST
            chosen = mix_candidates.select(pool, run.exclusions(), share, per_artist, run.rng, run.seed_tempos(seed))
            new_tracks = download_to_trial(run.conn, run.account, chosen, share, slot, run.now)
            budget -= len(new_tracks)
            run.downloaded += len(new_tracks)
        # Nothing new to fetch, or a disk limit reached: your own tracks take those places.
        picks += spare[:new_slots - len(trial_tracks) - len(new_tracks)]
        tracks = [_as_track(p) for p in picks] + trial_tracks + new_tracks
        run.rng.shuffle(tracks)
        publish(run.account, slot, f"Daily Mix+ {len(built) + 1}", _subtitle(seed), tracks, cover=seed_cover(run.stats, seed))
        run.remember("blend", [p.key for p in picks])
        built.append(slot)
    return built


def build_discover(run) -> list:
    """Only what you never heard, around your habits: new releases from the artists
    the profile's Deezer account follows, and tracks of the artists closest to
    your favorites."""
    from core.releases import load_releases

    size = run.download_room(run.settings["discover_size"])
    if size <= 0:
        return []
    today = datetime.fromtimestamp(run.now, tz=timezone.utc).date()
    since = (today - timedelta(days=mix_candidates.RELEASES_WINDOW_DAYS)).isoformat()
    rules = run.exclusions(played=run.taste.track_plays, never_played_only=True)
    new_share = round(size * mix_candidates.DISCOVER_RELEASE_SHARE)
    feed = load_releases(account_context.deezer_account_of(run.account))
    newest = mix_candidates.select(mix_candidates.release_pool(feed.get("releases", []), since),
                                   rules, new_share, mix_taste.PER_ARTIST, run.rng)
    around = mix_candidates.select(mix_candidates.habit_pool(run.conn, run.taste, run.ids, run.now),
                                   rules, size, mix_taste.PER_ARTIST, run.rng)
    taken, chosen = set(), []
    for candidate in [*newest, *around]:
        if candidate.base not in taken:
            taken.add(candidate.base)
            chosen.append(candidate)
    slot = run.playlist_id("discover")
    tracks = download_to_trial(run.conn, run.account, chosen, size, slot, run.now)
    run.downloaded += len(tracks)
    if not tracks:
        return []
    run.rng.shuffle(tracks)
    publish(run.account, slot, "Discover", "Only tracks you never heard", tracks)
    return [slot]


def publish_trial_playlist(conn, account) -> bool:
    """Every track in this account's quarantine, so one that left today's mix
    can still be heard."""
    from core.deezer import auto_id

    playlist_id = auto_id(account, "trial")
    rows = [r for r in trial.active(conn, account) if Path(r["path"]).exists()]
    if not rows:
        if config.get_preview_state(playlist_id):
            unpublish(playlist_id)
        return False
    publish(account, playlist_id, "On trial", f"{len(rows)} tracks waiting for a verdict", [_trial_track(r) for r in rows])
    return True


def review_trial(conn, stats_conn, account, now) -> dict:
    """The verdicts on one account's quarantine with its rules, then its trash.
    Plays come from its history as it is now, so plays a merge brought in count
    too, and stars from its Navidrome user only."""
    rules = trial.rules_from(load_settings(conn, account))
    marks = trial.navidrome_marks(conn, account, now) if rules.auto and rules.marks_count else None
    owned = {}
    if rules.auto:
        owned = library_copies()
    # Until 1.15, To review held the tracks whose trial had failed: sorted once.
    migrate = rules.auto and not mixes_db.get_meta(conn, key(account, "trial_rules_v2"))
    report = trial.evaluate(conn, account, trial.plays_since_download(conn, stats_conn, account), marks or {},
                            trial.paths_in_regular_playlists(), owned, now, rules, migrate=migrate)
    if migrate:
        mixes_db.set_meta(conn, key(account, "trial_rules_v2"), True)
    report["purged"] = trial.purge(conn, account, now, rules.trash_days)
    report["navidrome_marks"] = marks is not None
    return report


_COUNTS = ("kept", "review", "trashed", "deleted", "gone", "purged")


def review_quarantine(now=None, accounts=None):
    """Outside the generation too: every scheduler pass, after an import of plays,
    and after the rules change. Each account's quarantine with its own rules,
    plays and stars (all of them, or the accounts named). The counts of every
    account together, or None when there is nothing to look at."""
    if not _review_lock.acquire(blocking=False):
        return None
    now = int(now or time.time())
    try:
        conn = mixes_db.connect()
        try:
            owners_before = trial.owners(conn)
            waiting = [a for a in owners_before if accounts is None or a in accounts]
            if not waiting:
                return None
            total = {name: 0 for name in _COUNTS}
            total["navidrome_marks"] = False
            for account in waiting:
                stats_conn = stats_db.connect(account)
                try:
                    report = review_trial(conn, stats_conn, account, now)
                finally:
                    stats_conn.close()
                for name in _COUNTS:
                    total[name] += report[name]
                total["navidrome_marks"] = total["navidrome_marks"] or report["navidrome_marks"]
                if any(report[k] for k in _COUNTS):
                    logger.info("Quarantine of %s: %s", account, report)
            if any(total[k] for k in _COUNTS):
                # A verdict on a shared track changes the other profiles' lists too.
                refresh_trial_playlists(conn, sorted(set(owners_before) | set(trial.owners(conn))))
            return total
        finally:
            conn.close()
    finally:
        _review_lock.release()


def _refresh_library(progress) -> None:
    from core.library import refresh_library_cache_incremental_with_progress

    refresh_library_cache_incremental_with_progress(progress_cb=lambda **kw: None)


def generate(account, versions=None, progress=None, now=None) -> dict:
    """One run for one account. `versions`: what to build, by default what it
    turned on."""
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("Your mixes are already being generated")
    emit = progress or (lambda message: None)
    now = int(now or time.time())
    conn, stats_conn = mixes_db.connect(), stats_db.connect(account)
    try:
        settings = load_settings(conn, account)
        wanted = versions if versions is not None else enabled_versions(settings)
        mixes_db.set_meta(conn, key(account, "seeds_today"), [])
        emit("Checking the tracks on trial")
        with _review_lock:
            report = review_trial(conn, stats_conn, account, now)
        # Each account draws its own; the install's as it always did.
        seed_text = f"{now // DAY}" if account == stats_db.FIRST_ACCOUNT else f"{account}:{now // DAY}"
        run = _Run(conn, stats_conn, account, now, seed_text)
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
            mixes_db.set_meta(conn, key(account, f"last_{name}"), now)
            _drop_stale(account, name, built[name])
            _drop_replaced_mode(conn, account, name, built[name])
        if run.downloaded:
            emit("Refreshing the library")
            _refresh_library(emit)
        refresh_trial_playlists(conn, sorted({account, *trial.owners(conn)}))
        result = {"built": built, "notes": run.notes, "trial": report, "downloaded": run.downloaded}
        mixes_db.set_meta(conn, key(account, "last_run"), {"at": now, "notes": run.notes})
        return result
    finally:
        conn.close()
        stats_conn.close()
        _run_lock.release()


def _generated(account, name) -> list:
    """The IDs of this account's generated playlists of one kind."""
    from core.deezer import load_playlists, parse_auto_id

    found = []
    for playlist in load_playlists():
        parsed = parse_auto_id(playlist["id"])
        if parsed and parsed[0] == account and parsed[1] == name:
            found.append(playlist["id"])
    return found


def _drop_stale(account, name, kept) -> None:
    """A mix that could not be built today leaves, rather than stay out of date."""
    if name == "discover" and not kept:
        return  # Nothing new this week: last week's still has tracks to hear.
    for playlist_id in _generated(account, name):
        if playlist_id not in kept:
            unpublish(playlist_id)


def _remove_playlists(account, name) -> None:
    for playlist_id in _generated(account, name):
        unpublish(playlist_id)


def _drop_replaced_mode(conn, account, name, built) -> None:
    """Switching between the two mixes: the old ones leave once the new ones exist."""
    if built and name in ("daily", "blend") and load_settings(conn, account)["mix_mode"] == name:
        _remove_playlists(account, "blend" if name == "daily" else "daily")


def set_mix_mode(conn, account, mode) -> None:
    """Off removes the mixes. Files on trial stay on trial. Another mode is due at once,
    whenever it last ran: nothing else would bring its playlists back."""
    previous = load_settings(conn, account)["mix_mode"]
    save_settings(conn, account, {"mix_mode": mode})
    if mode == "off":
        _remove_playlists(account, "daily")
        _remove_playlists(account, "blend")
    elif mode != previous:
        mixes_db.set_meta(conn, key(account, f"last_{mode}"), 0)


def set_discover(conn, account, enabled) -> None:
    was_on = load_settings(conn, account)["discover"]
    save_settings(conn, account, {"discover": enabled})
    if not enabled:
        _remove_playlists(account, "discover")
    elif not was_on:
        mixes_db.set_meta(conn, key(account, "last_discover"), 0)


def due_versions(conn, account, now) -> list:
    settings = load_settings(conn, account)
    every = {"daily": settings["daily_hours"] * 3600, "blend": settings["daily_hours"] * 3600,
             "discover": settings["discover_days"] * DAY}
    return [name for name in enabled_versions(settings)
            if now - mixes_db.get_meta(conn, key(account, f"last_{name}"), 0) >= every[name]]


def forget_account(account_id, heir) -> None:
    """A Navidrome account being removed: its tracks in quarantine go to `heir`,
    so that no file is left without anyone to decide on it (where `heir` has the
    track already, its own verdict stays), and its own state goes. Its
    playlists are core/publish.py's business."""
    from core.deezer import auto_id

    conn = mixes_db.connect()
    try:
        tracks = [r["deezer_id"] for r in conn.execute("SELECT deezer_id FROM trial_tracks WHERE account_id=?", (account_id,))]
        conn.execute("UPDATE OR IGNORE trial_tracks SET account_id=? WHERE account_id=?", (heir, account_id))
        conn.execute("DELETE FROM trial_tracks WHERE account_id=?", (account_id,))
        conn.executemany("DELETE FROM meta WHERE key=?", [(key(account_id, name),) for name in PER_PROFILE_KEYS])
        conn.executemany("DELETE FROM mix_history WHERE mix_id=?", [(auto_id(account_id, n),) for n in ("daily", "blend")])
        conn.commit()
        for deezer_id in tracks:
            try:
                trial._settle(conn, deezer_id, int(time.time()))
            except (trial.TrialError, OSError) as e:
                logger.warning("Could not settle %s: %s", deezer_id, e)
        refresh_trial_playlists(conn, [heir])
    finally:
        conn.close()


def refresh_trial_playlists(conn, profiles=None) -> None:
    """The On trial playlist of these profiles (every one by default): a verdict
    on a shared track changes the others' too."""
    for account in profiles if profiles is not None else accounts():
        try:
            publish_trial_playlist(conn, account)
        except (OSError, ValueError) as e:
            logger.warning("Could not update the On trial playlist of %s: %s", account, e)


def tick(now=None) -> None:
    """Called by the scheduler: keeps the tempo analysis going, and starts what is
    due once most of the library has been measured, or the mixes would ignore tempo.
    One account at a time: the next one is started by a later pass."""
    if is_running():
        return
    now = int(now or time.time())
    try:
        review_quarantine(now)
    except Exception as e:
        logger.error("Could not review the quarantine: %s", e)
    conn = mixes_db.connect()
    try:
        profiles = accounts()
        wanted = {account: enabled_versions(load_settings(conn, account)) for account in profiles}
        mixes_on = any(wanted.values())
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
        due = None
        if analysed >= MIN_ANALYSED_SHARE:
            for account in profiles:
                versions = due_versions(conn, account, now) if wanted[account] else []
                if versions:
                    due = (account, versions)
                    break
    finally:
        conn.close()
    if due:
        start_task(*due)


def start_task(account, versions, title=None):
    """In the background, followed in Activity."""
    from core import nd_accounts
    from core.config import create_task, push_task_event

    if title is None:
        title = "Generating your mixes"
        if len(accounts()) > 1:
            title += f" ({(nd_accounts.get(account) or {}).get('label') or account})"
    task_id = create_task(title, kind="mixes", cancellable=True)

    def runner():
        try:
            result = generate(account, versions, progress=lambda m: push_task_event(task_id, m, stage="build"))
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
                    mixes_db.set_meta(conn, key(account, f"last_{name}"), int(time.time()))
            finally:
                conn.close()
            config.finish_cancelled(task_id, "Cancelled: the playlists already built stay. The next refresh runs as planned")
        except Exception as e:
            logger.error("Could not generate the mixes: %s", e)
            push_task_event(task_id, f"Could not generate the mixes: {e}", stage="error", done=True, error=True)

    threading.Thread(target=runner, daemon=True, name="mix-builder").start()
    return task_id
