"""Quarantine for the tracks the generated playlists download by themselves.

A track stays playable in <downloads>/trial/ for a while. What you play or mark in
Navidrome is kept; the rest waits for your decision, and nothing leaves without
it. A removed track spends 30 days in a trash, then only its name is remembered,
so it is never proposed again.

Every file operation goes through _inside(): whatever the database says, nothing
outside the trial folder or the trash is moved or deleted."""
import logging
import os
import shutil
import tempfile
from pathlib import Path

from core import config, deezer_dl, metadata_fix, stats_db
from core.utils import read_tags

logger = logging.getLogger(__name__)

DAY = 86400
TRIAL_DAYS = 30
TRASH_DAYS = 30
KEEP_PLAYS = 2
KEEP_RATING = 4
ON_TRIAL, KEPT, PENDING, TRASH, DELETED, GONE = "on_trial", "kept", "pending", "trash", "deleted", "gone"


class TrialError(Exception):
    pass


def trial_dir() -> Path:
    return deezer_dl.download_dir() / "trial"


def trash_dir() -> Path:
    return Path(config.DATA_DIR) / "trial_trash"


def _inside(path, *folders) -> Path:
    """The real location of a file, refused unless it is in one of the folders.
    Resolved first, so neither ".." nor a similarly named folder gets through."""
    real = Path(os.path.realpath(path))
    for folder in folders:
        if Path(os.path.realpath(folder)) in real.parents:
            return real
    raise TrialError(f"Refused: {path} is not in the quarantine")


def _free_name(folder: Path, name: str) -> Path:
    """Never overwrite: a kept track must not replace a file already there."""
    target = folder / name
    stem, suffix, number = target.stem, target.suffix, 2
    while target.exists():
        target = folder / f"{stem} ({number}){suffix}"
        number += 1
    return target


def add_download(conn, deezer_id, artist, title, album, path, mix_id, now) -> None:
    """Registers a file saved in the trial folder. A track already decided keeps
    its decision. Plays carry the file's tags, which can differ from Deezer's names
    ("Blooming" and "Blooming Kitty"), so the key comes from the file when it can."""
    path = Path(path)
    tags = read_tags(path) if path.exists() else {}
    names = stats_db.split_artists(tags.get("artist") or artist)
    title_for_key = tags.get("title") or title
    conn.execute(
        "INSERT OR IGNORE INTO trial_tracks(deezer_id, track_key, artist, title, album, path, size, mix_id,"
        " downloaded_at, trial_ends_at, state, state_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(deezer_id), stats_db.track_key(names, title_for_key), artist, title, album or "", str(path),
         path.stat().st_size if path.exists() else 0, mix_id, int(now), int(now) + TRIAL_DAYS * DAY, ON_TRIAL, int(now)),
    )
    conn.commit()


def get(conn, deezer_id):
    return conn.execute("SELECT * FROM trial_tracks WHERE deezer_id=?", (str(deezer_id),)).fetchone()


def _set(conn, deezer_id, state, now, reason="", path=None) -> None:
    if path is None:
        conn.execute("UPDATE trial_tracks SET state=?, state_at=?, reason=? WHERE deezer_id=?",
                     (state, int(now), reason, str(deezer_id)))
    else:
        conn.execute("UPDATE trial_tracks SET state=?, state_at=?, reason=?, path=? WHERE deezer_id=?",
                     (state, int(now), reason, str(path), str(deezer_id)))
    conn.commit()


def _rewrite_playlist(playlist_id) -> None:
    from core.deezer import playlist_title, write_playlist_outputs

    state = config.get_preview_state(playlist_id)
    if state and isinstance(state.get("rows"), list):
        write_playlist_outputs(playlist_id, playlist_title(playlist_id), state["rows"])


def _follow_move(old, new) -> None:
    """The history and the saved playlists keep pointing at the file."""
    conn = stats_db.connect()
    try:
        conn.execute("UPDATE tracks SET file_path=? WHERE file_path=?", (str(new), str(old)))
        conn.commit()
    finally:
        conn.close()
    for playlist_id, state in config.load_preview_state().items():
        rows = state.get("rows") if isinstance(state, dict) else None
        if not isinstance(rows, list) or not any(r.get("local_path") == str(old) for r in rows):
            continue

        def change(current, old=str(old), new=str(new)):
            for row in current.get("rows", []):
                if row.get("local_path") == old:
                    row["local_path"] = new
            return current

        config.modify_preview_state(playlist_id, change)
        try:
            _rewrite_playlist(playlist_id)
        except (OSError, ValueError) as e:
            logger.warning("Could not rewrite playlist %s: %s", playlist_id, e)


def _forget_file(path) -> None:
    """A removed track leaves the generated playlists, and a regular playlist shows
    it as missing again, like any file that disappeared."""
    for playlist_id, state in config.load_preview_state().items():
        rows = state.get("rows") if isinstance(state, dict) else None
        if not isinstance(rows, list) or not any(r.get("local_path") == str(path) for r in rows):
            continue

        def change(current, generated=str(playlist_id).startswith("auto-"), path=str(path)):
            kept = []
            for row in current.get("rows", []):
                if row.get("local_path") != path:
                    kept.append(row)
                elif not generated:
                    row.update({"matched": False, "local_path": None, "source_name": "", "convert": "❌"})
                    kept.append(row)
            current["rows"] = kept
            return current

        config.modify_preview_state(playlist_id, change)
        try:
            _rewrite_playlist(playlist_id)
        except (OSError, ValueError) as e:
            logger.warning("Could not rewrite playlist %s: %s", playlist_id, e)


def keep(conn, deezer_id, now, reason="Kept by hand") -> None:
    row = get(conn, deezer_id)
    if row is None or row["state"] not in (ON_TRIAL, PENDING):
        raise TrialError("This track is not waiting for a decision")
    source = _inside(row["path"], trial_dir())
    songs = deezer_dl.download_dir() / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    target = _free_name(songs, source.name)
    shutil.move(str(source), str(target))
    _set(conn, deezer_id, KEPT, now, reason, target)
    metadata_fix.move_file(conn, row["path"], target)
    _follow_move(row["path"], target)


def remove(conn, deezer_id, now) -> None:
    row = get(conn, deezer_id)
    if row is None or row["state"] not in (ON_TRIAL, PENDING):
        raise TrialError("This track is not waiting for a decision")
    source = _inside(row["path"], trial_dir())
    trash_dir().mkdir(parents=True, exist_ok=True)
    target = _free_name(trash_dir(), source.name)
    shutil.move(str(source), str(target))
    _set(conn, deezer_id, TRASH, now, "Removed", target)
    _forget_file(row["path"])


def remove_all_pending(conn, now) -> int:
    count = 0
    for row in conn.execute("SELECT deezer_id FROM trial_tracks WHERE state=?", (PENDING,)).fetchall():
        try:
            remove(conn, row["deezer_id"], now)
            count += 1
        except (TrialError, OSError) as e:
            logger.warning("Could not remove %s: %s", row["deezer_id"], e)
    return count


def restore(conn, deezer_id, now) -> None:
    """Taking a track back out of the trash is a decision to keep it."""
    row = get(conn, deezer_id)
    if row is None or row["state"] != TRASH:
        raise TrialError("This track is not in the trash")
    source = _inside(row["path"], trash_dir())
    songs = deezer_dl.download_dir() / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    target = _free_name(songs, source.name)
    shutil.move(str(source), str(target))
    _set(conn, deezer_id, KEPT, now, "Restored", target)


def purge(conn, now) -> int:
    """The only automatic deletion: what you removed, after 30 days in the trash."""
    count = 0
    limit = int(now) - TRASH_DAYS * DAY
    rows = conn.execute("SELECT * FROM trial_tracks WHERE state=? AND state_at<=?", (TRASH, limit)).fetchall()
    for row in rows:
        try:
            _inside(row["path"], trash_dir()).unlink(missing_ok=True)
        except (TrialError, OSError) as e:
            logger.warning("Could not purge %s: %s", row["deezer_id"], e)
            continue
        _set(conn, row["deezer_id"], DELETED, now, row["reason"])
        count += 1
    return count


def evaluate(conn, plays, marks, used_paths, owned_keys, now) -> dict:
    """The daily pass. plays: deezer id -> plays since download. marks: deezer id ->
    Navidrome's star and rating. used_paths: files regular playlists rely on.
    owned_keys: tracks you also have outside the quarantine."""
    report = {"kept": 0, "pending": 0, "gone": 0}
    rows = conn.execute("SELECT * FROM trial_tracks WHERE state IN (?, ?)", (ON_TRIAL, PENDING)).fetchall()
    for row in rows:
        deezer_id = row["deezer_id"]
        if not Path(row["path"]).exists():
            _set(conn, deezer_id, GONE, now, "The file is gone")
            report["gone"] += 1
            continue
        mark = marks.get(deezer_id) or {}
        reason = None
        if row["path"] in used_paths:
            reason = "In one of your playlists"
        elif row["track_key"] in owned_keys:
            reason = "Also in your library"
        elif plays.get(deezer_id, 0) >= KEEP_PLAYS:
            reason = f"Played {plays[deezer_id]} times"
        elif mark.get("starred"):
            reason = "Starred in Navidrome"
        elif (mark.get("rating") or 0) >= KEEP_RATING:
            reason = f"Rated {mark['rating']} in Navidrome"
        if reason:
            try:
                keep(conn, deezer_id, now, reason)
                report["kept"] += 1
            except (TrialError, OSError) as e:
                logger.warning("Could not keep %s: %s", deezer_id, e)
            continue
        if row["state"] == ON_TRIAL:
            rating = mark.get("rating") or 0
            if 0 < rating < 3:
                _set(conn, deezer_id, PENDING, now, f"Rated {rating} in Navidrome")
                report["pending"] += 1
            elif now >= row["trial_ends_at"]:
                played = plays.get(deezer_id, 0)
                _set(conn, deezer_id, PENDING, now, "Played once" if played else "Never played")
                report["pending"] += 1
    return report


def rejected(conn) -> dict:
    """What must never be proposed again."""
    rows = conn.execute("SELECT deezer_id, track_key FROM trial_tracks WHERE state IN (?, ?)", (TRASH, DELETED)).fetchall()
    return {"ids": {r["deezer_id"] for r in rows}, "keys": {r["track_key"] for r in rows}}


def active(conn) -> list:
    return conn.execute("SELECT * FROM trial_tracks WHERE state IN (?, ?) ORDER BY downloaded_at DESC",
                        (ON_TRIAL, PENDING)).fetchall()


def listing(conn, state) -> list:
    return conn.execute("SELECT * FROM trial_tracks WHERE state=? ORDER BY state_at DESC", (state,)).fetchall()


def plays_since_download(conn, stats_conn) -> dict:
    """deezer id -> plays since the track arrived, found by the key its plays carry."""
    found = {}
    for row in active(conn):
        count = stats_conn.execute(
            "SELECT COUNT(*) FROM plays p JOIN tracks t ON t.id = p.track_id WHERE t.key=? AND p.listened_at>=?",
            (row["track_key"], row["downloaded_at"]),
        ).fetchone()[0]
        if count:
            found[row["deezer_id"]] = count
    return found


def navidrome_marks(conn):
    """deezer id -> star and rating in Navidrome, from a copy of its database; None
    when it is not mounted. Only the files on trial are looked at."""
    from core import stats_import

    source = stats_import._navidrome_path()
    if not source.is_file():
        return None
    by_name = {f"trial/{Path(r['path']).name}": r["deezer_id"] for r in active(conn)}
    marks = {}
    with tempfile.TemporaryDirectory(dir=config.DATA_DIR) as folder:
        nd = stats_import._open_copy(source, Path(folder), "navidrome.db",
                                     {"media_file": {"id", "path"}, "annotation": {"item_id", "starred", "rating"}},
                                     "Navidrome")
        try:
            rows = nd.execute(
                "SELECT m.path, MAX(a.starred) AS starred, MAX(a.rating) AS rating FROM annotation a"
                " JOIN media_file m ON m.id = a.item_id WHERE a.item_type='media_file' GROUP BY m.path"
            ).fetchall()
        finally:
            nd.close()
    for row in rows:
        parts = Path(row["path"]).as_posix().split("/")
        deezer_id = by_name.get("/".join(parts[-2:]))
        if deezer_id:
            marks[deezer_id] = {"starred": bool(row["starred"]), "rating": row["rating"] or 0}
    return marks


def paths_in_regular_playlists() -> set:
    """Files your own playlists rely on. Generated playlists do not protect a track."""
    found = set()
    for playlist_id, state in config.load_preview_state().items():
        if str(playlist_id).startswith("auto-") or not isinstance(state, dict):
            continue
        for row in state.get("rows") or []:
            if row.get("local_path"):
                found.add(row["local_path"])
    return found


def usage(conn, plays) -> dict:
    """What the download limits look at. A track waiting for your decision still
    takes space, so it counts in the size."""
    rows = active(conn)
    return {
        "unheard": sum(1 for r in rows if r["state"] == ON_TRIAL and not plays.get(r["deezer_id"])),
        "bytes": sum(r["size"] for r in rows),
    }
