"""Builds the listening history from Navidrome and Maloja, and rebuilds it on demand.

Merge only adds plays and refreshes their details, so a file purged from
Navidrome cannot shrink the history. Start clean wipes it and uses only the
sources, which is why it needs Navidrome's database. Navidrome is the better
source (every play has a length), Maloja adds what Navidrome no longer has."""
import bisect
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from rapidfuzz import fuzz

from core import config, stats_db
from core.stats_db import add_play, clean_title, fold, set_track_artists, split_artists, track_key, upsert_album, upsert_track

logger = logging.getLogger(__name__)

SAME_PLAY_ANY_TITLE = 5
SAME_PLAY_WINDOW = 120
SAME_PLAY_SIMILARITY = 85
SAME_TRACK_WINDOW = 600
KEEP_BACKUPS = 3

NAVIDROME_DEFAULT = "/import/navidrome/navidrome.db"
MALOJA_DEFAULT = "/import/maloja/malojadb.sqlite"

NAVIDROME_NEEDS = {
    "scrobbles": {"media_file_id", "submission_time", "user_id"},
    "media_file": {"id", "title", "artist", "album", "album_artist", "duration", "tags", "participants"},
}
MALOJA_NEEDS = {
    "scrobbles": {"timestamp", "track_id", "duration"},
    "tracks": {"id", "title", "length", "album_id"},
    "artists": {"id", "name"},
    "trackartists": {"artist_id", "track_id"},
    "albums": {"id", "albtitle"},
    "albumartists": {"artist_id", "album_id"},
}

_running = threading.Lock()
_library_cache = {}


NO_USER = ("Navidrome's plays were not read: this profile is not linked to a Navidrome user yet."
           " Add its user name in Settings → Navidrome accounts, then test it.")


class ImportRefused(Exception):
    """The import cannot run; the message is shown to the user as it is."""


def maloja_account():
    """Maloja keeps one person's plays: those of the install, whose account was
    made from it (else the default one). No other profile reads it."""
    from core import nd_accounts

    return nd_accounts.owner_fallback() or stats_db.FIRST_ACCOUNT


def same_play(a_ts, a_key, a_title, b_ts, b_key, b_title) -> bool:
    """Sources rewrite titles, so two plays at the same moment are one play
    whatever they are called; further apart, the title has to agree too."""
    gap = abs(a_ts - b_ts)
    if gap <= SAME_PLAY_ANY_TITLE:
        return True
    if gap > SAME_PLAY_WINDOW:
        return False
    if a_key == b_key:
        return True
    return fuzz.token_set_ratio(fold(clean_title(a_title)), fold(clean_title(b_title))) >= SAME_PLAY_SIMILARITY


# --- Sources -------------------------------------------------------------------

def _navidrome_path() -> Path:
    return Path(os.environ.get("STATS_NAVIDROME_DB") or NAVIDROME_DEFAULT)


def _maloja_path() -> Path:
    return Path(os.environ.get("STATS_MALOJA_DB") or MALOJA_DEFAULT)


def _kept_maloja() -> Path:
    return Path(config.DATA_DIR) / "stats_sources" / "malojadb.sqlite"


def source_status(account) -> dict:
    from core import nd_accounts

    navidrome, maloja, kept = _navidrome_path(), _maloja_path(), _kept_maloja()
    kept_exists = kept.exists()
    profile = nd_accounts.get(account) or {}
    owner = maloja_account()
    used = account == owner
    return {
        "navidrome": {
            "path": str(navidrome),
            "found": navidrome.is_file(),
            "user": profile.get("username") or "",
            "linked": bool(profile.get("navidrome_user_id")),
        },
        "maloja": {
            "path": str(maloja),
            "found": maloja.is_file(),
            "kept_copy": kept_exists,
            "kept_at": int(kept.stat().st_mtime) if kept_exists else None,
            "used": used,
            "owner": (nd_accounts.get(owner) or {}).get("label") or owner or "",
        },
        "can_merge": navidrome.is_file() or (used and (maloja.is_file() or kept_exists)),
        "can_clean": navidrome.is_file(),
    }


def _open_copy(source: Path, folder: Path, name: str, needs: dict, label: str) -> sqlite3.Connection:
    """Reads a copy: the live file stays untouched, and copying its write-ahead
    log along keeps the most recent plays, which live only there for a while."""
    target = folder / name
    shutil.copyfile(source, target)
    wal = Path(f"{source}-wal")
    if wal.exists():
        shutil.copyfile(wal, Path(f"{target}-wal"))
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        for table, columns in needs.items():
            found = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if not found:
                raise ImportRefused(f"{label}'s database has no {table} table: its format may have changed.")
            missing = columns - found
            if missing:
                raise ImportRefused(f"{label}'s {table} table has no {', '.join(sorted(missing))} column: its format may have changed.")
    except sqlite3.DatabaseError as e:
        conn.close()
        raise ImportRefused(f"{label}'s database could not be read: {e}") from e
    except ImportRefused:
        conn.close()
        raise
    return conn


def _first_genre(tags_json):
    try:
        values = (json.loads(tags_json or "{}").get("genre") or [])
    except ValueError:
        return None
    for item in values:
        value = item.get("value") if isinstance(item, dict) else item
        if stats_db.usable_genre(value):
            return str(value).strip()
    return None


def _participants(participants_json, fallback):
    try:
        people = (json.loads(participants_json or "{}").get("artist") or [])
        names = [p.get("name") for p in people if isinstance(p, dict)]
    except ValueError:
        names = []
    return split_artists(names) or split_artists(fallback)


def _file_columns(conn) -> tuple:
    """Where each file is, for Navidrome versions that say so."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(media_file)")}
    library = {row[1] for row in conn.execute("PRAGMA table_info(library)")}
    if {"path", "library_id"} <= columns and {"id", "path"} <= library:
        return "f.path file_path, l.path library_path", "LEFT JOIN library l ON l.id = f.library_id"
    return "NULL file_path, NULL library_path", ""


def _navidrome_user(conn, account):
    """The Navidrome user whose plays are this profile's: the one its test
    found, else the one with its user name. On a Navidrome where a single user
    ever played, those plays are the install's, as they were before profiles."""
    from core import nd_accounts

    profile = nd_accounts.get(account) or {}
    try:
        users = {row["id"]: row["user_name"] or "" for row in conn.execute('SELECT id, user_name FROM "user"')}
    except sqlite3.DatabaseError:
        users = {}
    if profile.get("navidrome_user_id") in users:
        return profile["navidrome_user_id"]
    name = (profile.get("username") or "").strip().casefold()
    for user_id, user_name in users.items():
        if name and user_name.casefold() == name:
            return user_id
    if account == maloja_account():
        players = [row[0] for row in conn.execute("SELECT DISTINCT user_id FROM scrobbles LIMIT 2")]
        if len(players) == 1:
            return players[0]
    return None


def _read_navidrome(conn, user_id) -> list:
    """The plays of one Navidrome user: the others' are theirs."""
    from core.stats_files import container_path

    file_columns, library_join = _file_columns(conn)
    rows = conn.execute(
        "SELECT DISTINCT s.submission_time ts, s.media_file_id file, f.title, f.artist, f.album, f.album_artist,"
        f" f.duration, f.tags, f.participants, {file_columns}"
        f" FROM scrobbles s JOIN media_file f ON f.id = s.media_file_id {library_join}"
        " WHERE s.user_id = ? ORDER BY s.submission_time", (user_id,),
    ).fetchall()
    _, _, _, mappings = config.get_paths_from_config()
    return [{
        "path": container_path(row["library_path"], row["file_path"], mappings),
        "ts": int(row["ts"]),
        "title": row["title"] or "",
        "artists": _participants(row["participants"], row["artist"]),
        "album": row["album"],
        "album_artist": row["album_artist"],
        "duration": row["duration"] or None,
        "genre": _first_genre(row["tags"]),
    } for row in rows if row["title"]]


def _read_maloja(conn) -> list:
    artists_of = {}
    for row in conn.execute(
        "SELECT ta.track_id, a.name FROM trackartists ta JOIN artists a ON a.id = ta.artist_id ORDER BY ta.id"
    ):
        artists_of.setdefault(row["track_id"], []).append(row["name"])
    album_artist = {}
    for row in conn.execute(
        "SELECT aa.album_id, a.name FROM albumartists aa JOIN artists a ON a.id = aa.artist_id ORDER BY aa.id"
    ):
        album_artist.setdefault(row["album_id"], row["name"])
    rows = conn.execute(
        "SELECT s.timestamp ts, s.track_id, s.duration, t.title, t.length, t.album_id, al.albtitle"
        " FROM scrobbles s JOIN tracks t ON t.id = s.track_id LEFT JOIN albums al ON al.id = t.album_id"
        " ORDER BY s.timestamp"
    ).fetchall()
    return [{
        "ts": int(row["ts"]),
        "title": row["title"] or "",
        "artists": split_artists(artists_of.get(row["track_id"])),
        "album": row["albtitle"],
        "album_artist": album_artist.get(row["album_id"]),
        "duration": row["length"] or row["duration"] or None,
        "genre": None,
        "path": None,
    } for row in rows if row["title"]]


def _scrobble_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM scrobbles").fetchone()[0]


def _keep_maloja_copy(conn) -> None:
    kept = _kept_maloja()
    kept.parent.mkdir(parents=True, exist_ok=True)
    partial = kept.with_suffix(".tmp")
    target = sqlite3.connect(partial)
    try:
        conn.backup(target)
    finally:
        target.close()
    partial.replace(kept)


def _load_saved_maloja(folder: Path, warnings: list):
    """The saved copy, or None: a damaged one must not stop the other sources."""
    kept = _kept_maloja()
    if not kept.exists():
        return None
    try:
        return _open_copy(kept, folder, "kept.db", MALOJA_NEEDS, "The saved Maloja copy")
    except (ImportRefused, sqlite3.DatabaseError, OSError) as e:
        warnings.append(f"The saved Maloja copy could not be used: {e}")
        return None


def _load_sources(account, folder: Path, warnings: list, keep_copy=True) -> tuple:
    navidrome_plays, maloja_plays = [], []
    navidrome, maloja = _navidrome_path(), _maloja_path()
    try:
        if navidrome.is_file():
            conn = _open_copy(navidrome, folder, "navidrome.db", NAVIDROME_NEEDS, "Navidrome")
            try:
                user_id = _navidrome_user(conn, account)
                if user_id is not None:
                    navidrome_plays = _read_navidrome(conn, user_id)
                elif conn.execute("SELECT 1 FROM scrobbles LIMIT 1").fetchone():
                    warnings.append(NO_USER)
            finally:
                conn.close()
        else:
            warnings.append("Navidrome's database is not mounted: its new plays were not read.")
    except sqlite3.DatabaseError as e:
        raise ImportRefused(f"Navidrome's database could not be read: {e}") from e
    if account != maloja_account():
        return navidrome_plays, maloja_plays

    live = saved = None
    try:
        saved = _load_saved_maloja(folder, warnings)
        saved_count = -1
        if saved:
            try:
                saved_count = _scrobble_count(saved)
            except sqlite3.DatabaseError as e:
                warnings.append(f"The saved Maloja copy could not be used: {e}")
                saved.close()
                saved = None
        if maloja.is_file():
            live = _open_copy(maloja, folder, "maloja.db", MALOJA_NEEDS, "Maloja")
            if _scrobble_count(live) >= saved_count:
                # Read first: a file that cannot be read must not replace a good copy.
                maloja_plays = _read_maloja(live)
                if keep_copy:
                    _keep_maloja_copy(live)
                return navidrome_plays, maloja_plays
            warnings.append("The mounted Maloja database has fewer plays than the saved copy: the saved copy was used.")
    except sqlite3.DatabaseError as e:
        raise ImportRefused(f"Maloja's database could not be read: {e}") from e
    finally:
        if live:
            live.close()

    try:
        if saved:
            maloja_plays = _read_maloja(saved)
    except sqlite3.DatabaseError as e:
        warnings.append(f"The saved Maloja copy could not be used: {e}")
    finally:
        if saved:
            saved.close()
    return navidrome_plays, maloja_plays


def _library_index() -> dict:
    """Track lengths and file paths from the library index, by track key."""
    from core.library import load_library_cache

    _, _, cache_file, _ = config.get_paths_from_config()
    try:
        stamp = cache_file.stat().st_mtime_ns
    except OSError:
        return {"durations": {}, "paths": {}}
    if _library_cache.get("stamp") != stamp:
        durations, paths = {}, {}
        for entry in load_library_cache(cache_file):
            if not entry.get("tag_title"):
                continue
            key = track_key(split_artists(entry.get("tag_artist")), entry["tag_title"])
            if entry.get("duration"):
                durations[key] = float(entry["duration"])
            if entry.get("path"):
                paths[key] = entry["path"]
        _library_cache.update(stamp=stamp, durations=durations, paths=paths)
    return _library_cache


def library_durations() -> dict:
    return _library_index()["durations"]


def library_paths() -> dict:
    return _library_index()["paths"]


# --- Writing -------------------------------------------------------------------

def _backup(account) -> str:
    """A copy beside the history (stats.db.bak-… for the first account), the
    last ones kept."""
    path = stats_db.db_path(account)
    source = sqlite3.connect(path)
    name = f"{path.name}.bak-{time.time_ns()}"
    target = sqlite3.connect(path.parent / name)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    backups = sorted(path.parent.glob(f"{path.name}.bak-*"), key=lambda p: int(p.name.rsplit("-", 1)[1]))
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()
    return name


class _Stored:
    """Plays already in the database, sorted by time, for matching by moment."""

    def __init__(self, conn):
        rows = conn.execute(
            "SELECT p.id, p.listened_at ts, t.key, t.title, p.source FROM plays p"
            " JOIN tracks t ON t.id = p.track_id ORDER BY p.listened_at, p.id"
        ).fetchall()
        self.items = [dict(row) for row in rows]
        self.times = [item["ts"] for item in self.items]
        self.used = set()

    def near(self, ts, window=SAME_PLAY_WINDOW):
        low = bisect.bisect_left(self.times, ts - window)
        high = bisect.bisect_right(self.times, ts + window)
        found = self.items[low:high]
        found.sort(key=lambda item: abs(item["ts"] - ts))
        return found

    def add(self, item):
        position = bisect.bisect_right(self.times, item["ts"])
        self.times.insert(position, item["ts"])
        self.items.insert(position, item)

    def remove(self, item):
        position = next(i for i in range(bisect.bisect_left(self.times, item["ts"]), len(self.items)) if self.items[i] is item)
        del self.items[position]
        del self.times[position]

    def move(self, item, ts):
        self.remove(item)
        item["ts"] = ts
        self.add(item)


def _rekey_tracks(conn) -> int:
    """Applies the current key rule to stored tracks, joining those that now
    count as one. Returns how many plays turned out to be the same play."""
    merged = 0
    for track in conn.execute("SELECT id, key, title FROM tracks").fetchall():
        names = [r[0] for r in conn.execute(
            "SELECT a.name FROM track_artists ta JOIN artists a ON a.id = ta.artist_id"
            " WHERE ta.track_id = ? ORDER BY ta.position", (track["id"],))]
        key = track_key(names, track["title"])
        if key == track["key"]:
            continue
        other = conn.execute("SELECT id FROM tracks WHERE key = ?", (key,)).fetchone()
        if other is None:
            conn.execute("UPDATE tracks SET key = ? WHERE id = ?", (key, track["id"]))
            continue
        conn.execute("UPDATE OR IGNORE plays SET track_id = ? WHERE track_id = ?", (other[0], track["id"]))
        merged += conn.execute("DELETE FROM plays WHERE track_id = ?", (track["id"],)).rowcount
        conn.execute("DELETE FROM tracks WHERE id = ?", (track["id"],))
    return merged


def _wipe(conn) -> None:
    for table in ("plays", "track_artists", "tracks", "albums", "artists"):
        conn.execute(f"DELETE FROM {table}")


def _point_play(conn, play_id, track_id, album_id, duration, listened_at) -> tuple:
    """Gives a stored play Navidrome's details and time, so the next run finds
    it again at that exact moment. Returns (updated, merged)."""
    row = conn.execute("SELECT track_id, album_id, duration_sec, listened_at, source FROM plays WHERE id = ?", (play_id,)).fetchone()
    duration = duration or row["duration_sec"]
    wanted = (track_id, album_id, duration, listened_at, "navidrome")
    if tuple(row) == wanted:
        return 0, 0
    try:
        conn.execute(
            "UPDATE plays SET track_id = ?, album_id = ?, duration_sec = ?, listened_at = ?, source = ? WHERE id = ?",
            (*wanted, play_id),
        )
        return 1, 0
    except sqlite3.IntegrityError:
        # Another row already says the same track at the same moment: one play.
        conn.execute("DELETE FROM plays WHERE id = ?", (play_id,))
        return 0, 1


def _apply_navidrome(conn, plays, stored, report) -> None:
    def take(match, play, key, track_id, album_id):
        stored.used.add(match["id"])
        updated, merged = _point_play(conn, match["id"], track_id, album_id, play["duration"], play["ts"])
        report["updated"] += updated
        report["merged"] += merged
        if merged:
            stored.remove(match)
        else:
            match.update(key=key, title=play["title"], source="navidrome")
            stored.move(match, play["ts"])

    # The same track at the same moment first, so that a looser match below
    # cannot take a play that has its exact twin in the source.
    remaining = []
    for play in plays:
        key = track_key(play["artists"], play["title"])
        track_id = upsert_track(conn, play["title"], play["artists"], duration=play["duration"],
                                duration_source="navidrome", genre=play["genre"], genre_source="navidrome")
        album_id = upsert_album(conn, play["album"], play["album_artist"])
        if album_id and play["path"]:
            conn.execute("UPDATE albums SET file_path = ? WHERE id = ?", (play["path"], album_id))
        exact = next((i for i in stored.near(play["ts"], 0) if i["id"] not in stored.used and i["key"] == key), None)
        if exact:
            take(exact, play, key, track_id, album_id)
        else:
            remaining.append((play, key, track_id, album_id))

    for play, key, track_id, album_id in remaining:
        match = None
        for item in stored.near(play["ts"]):
            if item["id"] in stored.used:
                continue
            if item["source"] == "navidrome":
                if item["ts"] == play["ts"]:  # the same play, retagged
                    match = item
                    break
                continue
            if same_play(play["ts"], key, play["title"], item["ts"], item["key"], item["title"]):
                match = item
                break
        if match:
            take(match, play, key, track_id, album_id)
            continue
        if add_play(conn, track_id, album_id, play["duration"], play["ts"], "navidrome"):
            row = conn.execute("SELECT id FROM plays WHERE track_id = ? AND listened_at = ?", (track_id, play["ts"])).fetchone()
            stored.add({"id": row[0], "ts": play["ts"], "key": key, "title": play["title"], "source": "navidrome"})
            stored.used.add(row[0])
            report["from_navidrome"] += 1

    # The newest file of each track decides its title and credits.
    seen = set()
    for play in reversed(plays):
        key = track_key(play["artists"], play["title"])
        if key in seen:
            continue
        seen.add(key)
        track_id = conn.execute("SELECT id FROM tracks WHERE key = ?", (key,)).fetchone()[0]
        conn.execute(
            "UPDATE tracks SET title = ?, artist_display = ?, file_path = COALESCE(?, file_path),"
            " duration_sec = COALESCE(?, duration_sec),"
            " duration_source = CASE WHEN ? IS NULL THEN duration_source ELSE 'navidrome' END,"
            " genre = COALESCE(?, genre),"
            " genre_source = CASE WHEN ? IS NULL THEN genre_source ELSE 'navidrome' END"
            " WHERE id = ?",
            (play["title"], " • ".join(dict.fromkeys(play["artists"])), play["path"], play["duration"], play["duration"],
             play["genre"], play["genre"], track_id),
        )
        set_track_artists(conn, track_id, play["artists"])


def _apply_maloja(conn, plays, stored, report, mode, navidrome_plays) -> None:
    """A Maloja play once paired stays paired: its partner's title may change
    later, and matching again would then count the play twice."""
    stored.used = set()
    pairs = dict(conn.execute("SELECT maloja_ts, partner_ts FROM maloja_pairs").fetchall())
    navidrome_times = {play["ts"] for play in navidrome_plays}

    def pair(play, key, partner):
        stored.used.add(partner["id"])
        conn.execute("INSERT OR REPLACE INTO maloja_pairs(maloja_ts, partner_ts) VALUES (?, ?)", (play["ts"], partner["ts"]))
        # An earlier run may have stored it alone, before its partner was known.
        for item in stored.near(play["ts"], 0):
            if item["source"] == "maloja" and item["key"] == key:
                conn.execute("DELETE FROM plays WHERE id = ?", (item["id"],))
                stored.remove(item)
                report["merged"] += 1
                break

    # First the plays that clearly line up, so a loose pairing below cannot
    # take a partner away from them.
    keyed = []
    for play in plays:
        key = track_key(play["artists"], play["title"])
        partner_ts = pairs.get(play["ts"])
        if partner_ts is not None and (mode == "merge" or partner_ts in navidrome_times):
            partner = next((i for i in stored.near(partner_ts, 0) if i["source"] != "maloja" and i["id"] not in stored.used), None)
            if partner:
                stored.used.add(partner["id"])
            continue
        keyed.append((play, key))

    remaining = []
    for play, key in keyed:
        match = next((
            item for item in stored.near(play["ts"])
            if item["source"] != "maloja" and item["id"] not in stored.used
            and same_play(play["ts"], key, play["title"], item["ts"], item["key"], item["title"])
        ), None)
        if match:
            pair(play, key, match)
        else:
            remaining.append((play, key))

    # Then the same track a few minutes away with no partner yet: Maloja's
    # timestamps drifted by minutes on some evenings.
    for play, key in remaining:
        match = next((
            item for item in stored.near(play["ts"], SAME_TRACK_WINDOW)
            if item["source"] != "maloja" and item["id"] not in stored.used and item["key"] == key
        ), None)
        if match:
            pair(play, key, match)
            continue
        if any(i["source"] == "maloja" and i["ts"] == play["ts"] and i["key"] == key for i in stored.near(play["ts"], 0)):
            continue  # imported by an earlier run
        track_id = upsert_track(conn, play["title"], play["artists"], duration=play["duration"], duration_source="maloja")
        album_id = upsert_album(conn, play["album"], play["album_artist"])
        if add_play(conn, track_id, album_id, play["duration"], play["ts"], "maloja"):
            row = conn.execute("SELECT id FROM plays WHERE track_id = ? AND listened_at = ?", (track_id, play["ts"])).fetchone()
            stored.add({"id": row[0], "ts": play["ts"], "key": key, "title": play["title"], "source": "maloja"})
            report["from_maloja"] += 1


def _fill_lengths(conn) -> None:
    durations = library_durations()
    for track in conn.execute("SELECT id, key FROM tracks WHERE duration_sec IS NULL").fetchall():
        duration = durations.get(track["key"])
        if duration:
            conn.execute("UPDATE tracks SET duration_sec = ?, duration_source = 'library' WHERE id = ?", (duration, track["id"]))


def _remove_orphans(conn) -> None:
    conn.execute("DELETE FROM tracks WHERE id NOT IN (SELECT track_id FROM plays)")
    conn.execute("DELETE FROM albums WHERE id NOT IN (SELECT album_id FROM plays WHERE album_id IS NOT NULL)")
    conn.execute("DELETE FROM artists WHERE id NOT IN (SELECT artist_id FROM track_artists)")


def _count_removed(old_plays, conn) -> int:
    stored = _Stored(conn)
    removed = 0
    for old in old_plays:
        match = next((
            item for item in stored.near(old["ts"])
            if item["id"] not in stored.used
            and same_play(old["ts"], old["key"], old["title"], item["ts"], item["key"], item["title"])
        ), None)
        if match:
            stored.used.add(match["id"])
        else:
            removed += 1
    return removed


def check_can_run(account, mode: str) -> None:
    if mode not in ("merge", "clean"):
        raise ValueError(f"Unknown import mode: {mode}")
    status = source_status(account)
    if mode == "clean" and not status["can_clean"]:
        raise ImportRefused(f"Start clean needs Navidrome's database, and it was not found at {status['navidrome']['path']}.")
    if not status["can_merge"]:
        raise ImportRefused("No source found: mount Navidrome's or Maloja's database first.")


def _plays_since(conn, last_id) -> list:
    """Plays that arrived after the sources were read: they cannot be in them."""
    plays = []
    for row in conn.execute(
        "SELECT p.id, p.listened_at, p.track_id, p.duration_sec, t.title, al.title album, al.album_artist"
        " FROM plays p JOIN tracks t ON t.id = p.track_id LEFT JOIN albums al ON al.id = p.album_id"
        " WHERE p.id > ? AND p.source = 'live'", (last_id,),
    ).fetchall():
        artists = [r[0] for r in conn.execute(
            "SELECT a.name FROM track_artists ta JOIN artists a ON a.id = ta.artist_id"
            " WHERE ta.track_id = ? ORDER BY ta.position", (row["track_id"],))]
        plays.append({**dict(row), "artists": artists})
    return plays


def run_import(account, mode: str, progress=None, dry_run=False) -> dict:
    """Rebuilds one account's history. `dry_run` works out the same report and
    leaves everything as it was."""
    check_can_run(account, mode)
    say = progress or (lambda message, percent=None: None)

    report = {
        "mode": mode, "started_at": int(time.time()), "finished_at": None, "before": 0, "after": 0,
        "added": 0, "updated": 0, "merged": 0, "removed": 0, "from_navidrome": 0, "from_maloja": 0,
        "maloja_only": 0, "read_navidrome": 0, "read_maloja": 0, "backup": None, "warnings": [],
    }
    conn = stats_db.connect(account)
    try:
        last_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM plays").fetchone()[0]
        folder = Path(tempfile.mkdtemp(prefix="stats_import", dir=config.DATA_DIR))
        try:
            say("Reading the sources", 5)
            if dry_run:
                navidrome_plays, maloja_plays = _load_sources(account, folder, report["warnings"], False)
            else:
                navidrome_plays, maloja_plays = _load_sources(account, folder, report["warnings"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        report["read_navidrome"] = len(navidrome_plays)
        report["read_maloja"] = len(maloja_plays)
        if mode == "clean" and not navidrome_plays:
            if NO_USER in report["warnings"]:
                raise ImportRefused("Start clean needs this profile's Navidrome user: add its user name in"
                                    " Settings → Navidrome accounts, then test it. Nothing was changed.")
            raise ImportRefused("Navidrome's database has no plays, so Start clean would empty your history. Nothing was changed.")

        if not dry_run:
            say("Backing up the current history", 30)
            report["backup"] = _backup(account)
        conn.execute("BEGIN IMMEDIATE")
        try:
            report["before"] = stats_db.play_count(conn)
            old_plays = []
            if mode == "clean":
                old_plays = _Stored(conn).items
                arrived = _plays_since(conn, last_id)
                _wipe(conn)
                for play in arrived:
                    track_id = upsert_track(conn, play["title"], play["artists"])
                    add_play(conn, track_id, upsert_album(conn, play["album"], play["album_artist"]),
                             play["duration_sec"], play["listened_at"], "live")
            else:
                report["merged"] += _rekey_tracks(conn)
            stored = _Stored(conn)
            say("Adding Navidrome's plays", 45)
            _apply_navidrome(conn, navidrome_plays, stored, report)
            say("Adding Maloja's plays", 75)
            _apply_maloja(conn, maloja_plays, stored, report, mode, navidrome_plays)
            _fill_lengths(conn)
            _remove_orphans(conn)
            if not dry_run:
                from core.stats_covers import refresh_after_merge
                refresh_after_merge(conn)
            report["added"] = report["from_navidrome"] + report["from_maloja"]
            report["after"] = stats_db.play_count(conn)
            report["maloja_only"] = conn.execute("SELECT COUNT(*) FROM plays WHERE source = 'maloja'").fetchone()[0]
            if mode == "clean":
                report["removed"] = _count_removed(old_plays, conn)
            report["finished_at"] = int(time.time())
            if dry_run:
                conn.rollback()
            else:
                stats_db.set_meta(conn, "last_import", report)
                conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    if not dry_run and account == maloja_account():
        # Plays just merged may decide tracks in quarantine: no need to wait.
        try:
            from core import mix_builder
            mix_builder.review_quarantine()
        except Exception as e:
            logger.warning("Could not review the quarantine after the import: %s", e)
    return report


def preview_clean(account) -> dict:
    """What Start clean would do, for its confirmation."""
    return run_import(account, "clean", dry_run=True)


def import_running() -> bool:
    return _running.locked()


def start_import_task(account, mode: str) -> str:
    """Runs the import of one account's history in the background, listed in
    Activity. One rebuild at a time, whoever it is for."""
    from core import nd_accounts

    check_can_run(account, mode)
    if not _running.acquire(blocking=False):
        raise ImportRefused("A rebuild is already running.")
    title = "Stats history: start clean" if mode == "clean" else "Stats history: merge"
    if len(nd_accounts.list_accounts()) > 1:
        title += f" ({(nd_accounts.get(account) or {}).get('label') or account})"
    try:
        task_id = config.create_task(title, kind="stats", cancellable=True)

        def work():
            try:
                report = run_import(account, mode, lambda message, percent=None: config.push_task_event(task_id, message=message, progress=percent))
                summary = f"{report['after']} plays: {report['added']} added, {report['updated']} updated"
                if report["removed"]:
                    summary += f", {report['removed']} removed"
                config.push_task_event(task_id, f"Done: {summary}", stage="done", progress=100, done=True)
            except config.TaskCancelled:
                # The whole rebuild is one transaction: it was rolled back.
                config.finish_cancelled(task_id, "Cancelled: your history is unchanged")
            except ImportRefused as e:
                config.push_task_event(task_id, str(e), stage="error", done=True, error=True)
            except Exception as e:
                logger.exception("Stats import failed")
                config.push_task_event(task_id, f"The rebuild failed and changed nothing: {e}", stage="error", done=True, error=True)
            finally:
                _running.release()

        threading.Thread(target=work, daemon=True, name="stats-import").start()
    except BaseException:
        _running.release()
        raise
    return task_id
