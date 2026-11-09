"""Quarantine for the tracks the generated playlists download by themselves.

A track stays playable in <downloads>/trial/ for a while. One you play enough, or
star in Navidrome, waits under To review for you to keep it, or is kept at once
with Bypass user review. One that does not earn its place by the end of the trial
goes to the trash, or is deleted at once if you chose so. After its days in the
trash, only its name is remembered, so it is never proposed again. Every rule is
in Rules, from the settings in Manage.

Every file operation goes through _inside(): whatever the database says, nothing
outside the trial folder or the trash is moved or deleted.

The quarantine is shared by the Navidrome profiles: a track has one file and a
verdict from each profile that got it. A track on trial for one profile can be
given to another without downloading it again. Kept by one, it goes to the
library, for everyone. Turned down by one, it only leaves that profile: the file
goes to the trash once no other profile still has it on trial, and never while
another profile's own playlist uses it, in which case it goes to the library."""
import logging
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from core import config, deezer_dl, metadata_fix, stats_db
from core.utils import FILES_LOCK, read_tags

logger = logging.getLogger(__name__)

DAY = 86400
TRIAL_DAYS = 30
TRASH_DAYS = 30
KEEP_PLAYS = 2
KEEP_RATING = 4
BAD_RATING = 2
MARKS_EVERY = 3600
ON_TRIAL, KEPT, PENDING, TRASH, DELETED, GONE = "on_trial", "kept", "pending", "trash", "deleted", "gone"
ACTIVE = (ON_TRIAL, PENDING)


class TrialError(Exception):
    pass


@dataclass(frozen=True)
class Rules:
    """What the daily pass may decide on its own. Off: nothing moves by itself."""
    auto: bool = True
    trial_days: int = TRIAL_DAYS
    trash_days: int = TRASH_DAYS
    delete_at_end: bool = False
    bypass: bool = False
    plays_needed: int = KEEP_PLAYS
    marks_count: bool = True


def rules_from(settings) -> Rules:
    return Rules(auto=settings["trial_auto"], trial_days=settings["trial_days"], trash_days=settings["trash_days"],
                 delete_at_end=settings["trial_delete"], bypass=settings["trial_bypass"],
                 plays_needed=settings["trial_plays"], marks_count=settings["trial_marks"])


def trial_ends_at(row, rules) -> int:
    """From the download date: a new trial length applies to tracks already there."""
    return row["downloaded_at"] + rules.trial_days * DAY


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


def add_download(conn, account, deezer_id, artist, title, album, path, mix_id, now) -> None:
    """Registers a file saved in the trial folder, in this account's quarantine.
    A track already decided keeps its decision, and its owner. Plays carry the
    file's tags, which can differ from Deezer's names ("Blooming" and "Blooming
    Kitty"), so the key comes from the file when it can."""
    path = Path(path)
    tags = read_tags(path) if path.exists() else {}
    names = stats_db.split_artists(tags.get("artist") or artist)
    title_for_key = tags.get("title") or title
    conn.execute(
        "INSERT OR IGNORE INTO trial_tracks(deezer_id, track_key, artist, title, album, path, size, mix_id,"
        " downloaded_at, trial_ends_at, state, state_at, account_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(deezer_id), stats_db.track_key(names, title_for_key), artist, title, album or "", str(path),
         path.stat().st_size if path.exists() else 0, mix_id, int(now), int(now) + TRIAL_DAYS * DAY, ON_TRIAL, int(now),
         stats_db.checked_account(account)),
    )
    conn.commit()


def get(conn, deezer_id, account):
    """This profile's row for the track: its own verdict."""
    return conn.execute("SELECT * FROM trial_tracks WHERE deezer_id=? AND account_id=?",
                        (str(deezer_id), account)).fetchone()


def rows_of(conn, deezer_id) -> list:
    """Every profile's row for the track: one file, a verdict each."""
    return conn.execute("SELECT * FROM trial_tracks WHERE deezer_id=? ORDER BY account_id", (str(deezer_id),)).fetchall()


def file_row(conn, deezer_id):
    """A row that knows where the track's file is now, whoever's it is."""
    return next((r for r in rows_of(conn, deezer_id) if r["state"] in (*ACTIVE, TRASH, KEPT) and r["path"]), None)


def accounts_of(conn, deezer_id) -> list:
    return [r["account_id"] for r in rows_of(conn, deezer_id)]


def shared_with(conn, account) -> dict:
    """deezer id -> the other profiles that also have it on trial or to review,
    for this profile's tracks."""
    found = {}
    for row in conn.execute(
        "SELECT o.deezer_id, o.account_id FROM trial_tracks t JOIN trial_tracks o ON o.deezer_id = t.deezer_id"
        " AND o.account_id != t.account_id WHERE t.account_id=? AND o.state IN (?, ?) ORDER BY o.account_id",
        (account, *ACTIVE),
    ):
        found.setdefault(row["deezer_id"], []).append(row["account_id"])
    return found


def _set(conn, deezer_id, account, state, now, reason="", path=None) -> None:
    if path is None:
        conn.execute("UPDATE trial_tracks SET state=?, state_at=?, reason=? WHERE deezer_id=? AND account_id=?",
                     (state, int(now), reason, str(deezer_id), account))
    else:
        conn.execute("UPDATE trial_tracks SET state=?, state_at=?, reason=?, path=? WHERE deezer_id=? AND account_id=?",
                     (state, int(now), reason, str(path), str(deezer_id), account))
    conn.commit()


def label(account) -> str:
    from core import nd_accounts

    return (nd_accounts.get(account) or {}).get("label") or account


def _still_on_trial(conn, deezer_id) -> bool:
    return any(r["state"] in ACTIVE for r in rows_of(conn, deezer_id))


def _holder(rows):
    """The row whose path is where the file is, while it is on trial or in a trash."""
    return next((r for r in rows if r["state"] in (*ACTIVE, TRASH) and r["path"] and Path(r["path"]).exists()), None)


def _rewrite_playlist(playlist_id) -> None:
    from core import publish
    from core.deezer import playlist_title

    state = config.get_preview_state(playlist_id)
    if state and isinstance(state.get("rows"), list):
        publish.publish(playlist_id, playlist_title(playlist_id), state["rows"])


def _follow_move(old, new) -> None:
    """Every history and the saved playlists keep pointing at the file."""
    for account in stats_db.accounts_with_history():
        conn = stats_db.connect(account)
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


def _drop_from_generated(path, account) -> None:
    """A profile turned the track down while another still has it on trial: the
    file stays, and only leaves this profile's generated playlists."""
    from core.deezer import parse_auto_id

    for playlist_id, state in config.load_preview_state().items():
        parsed = parse_auto_id(playlist_id)
        rows = state.get("rows") if isinstance(state, dict) else None
        if not parsed or parsed[0] != account or not isinstance(rows, list) \
                or not any(r.get("local_path") == str(path) for r in rows):
            continue

        def change(current, path=str(path)):
            current["rows"] = [r for r in current.get("rows", []) if r.get("local_path") != path]
            return current

        config.modify_preview_state(playlist_id, change)
        try:
            _rewrite_playlist(playlist_id)
        except (OSError, ValueError) as e:
            logger.warning("Could not rewrite playlist %s: %s", playlist_id, e)


def _to_library(conn, deezer_id, source, now, by) -> Path:
    """Moves the track's file into the library, for every profile: those that
    still had it on trial see it kept by `by`; those that had turned it down
    keep their refusal, with nothing waiting in a trash any more."""
    songs = deezer_dl.download_dir() / "songs"
    songs.mkdir(parents=True, exist_ok=True)
    target = _free_name(songs, source.name)
    with FILES_LOCK:
        shutil.move(str(source), str(target))
    for row in rows_of(conn, deezer_id):
        if row["account_id"] == by:
            continue
        if row["state"] in ACTIVE:
            _set(conn, deezer_id, row["account_id"], KEPT, now, f"Kept by {label(by)}", target)
        elif row["state"] == TRASH:
            _set(conn, deezer_id, row["account_id"], DELETED, now, row["reason"])
    return target


def _settle(conn, deezer_id, now, path=None) -> None:
    """Once a profile is done with the track, its one file goes where the other
    rows say: it stays on trial while a profile still has it there, waits in
    the trash while one still lets it, and goes when everyone is done. `path`:
    where the file of the profile just done with it is."""
    rows = rows_of(conn, deezer_id)
    holder = _holder(rows)
    known = holder["path"] if holder else path
    if not known or not Path(known).exists():
        return
    try:
        current = _inside(known, trial_dir(), trash_dir())
    except TrialError:
        return
    states = {r["state"] for r in rows}
    if states & set(ACTIVE):
        return
    if TRASH in states:
        if Path(os.path.realpath(trash_dir())) in current.parents:
            return
        trash_dir().mkdir(parents=True, exist_ok=True)
        target = _free_name(trash_dir(), current.name)
        with FILES_LOCK:
            shutil.move(str(current), str(target))
        conn.execute("UPDATE trial_tracks SET path=? WHERE deezer_id=? AND state=?", (str(target), str(deezer_id), TRASH))
        conn.commit()
        metadata_fix.move_file(conn, known, target)
    else:
        with FILES_LOCK:
            current.unlink(missing_ok=True)
    _forget_file(known)


def _keep_for_others(conn, row, account, now) -> bool:
    """A file another profile's own playlist relies on never goes to the trash:
    once no profile has it on trial any more, it goes to the library."""
    others = _playlist_owners(row["path"]) - {account}
    if not others or _still_on_trial(conn, row["deezer_id"]):
        return False
    source = _inside(row["path"], trial_dir())
    target = _to_library(conn, row["deezer_id"], source, now, account)
    current = get(conn, row["deezer_id"], account)
    _set(conn, row["deezer_id"], account, DELETED, now, current["reason"] if current else "")
    metadata_fix.move_file(conn, row["path"], target)
    _follow_move(row["path"], target)
    return True


def share(conn, account, deezer_id, mix_id, now) -> bool:
    """Puts a track another profile already has into this one's quarantine,
    without downloading it again: its file is on trial, or waits in another
    profile's trash, and then comes back to the trial folder. False when there
    is no file to share."""
    if get(conn, deezer_id, account) is not None:
        return False
    rows = rows_of(conn, deezer_id)
    holder = _holder(rows)
    if holder is None:
        return False
    path = Path(holder["path"])
    try:
        _inside(path, trial_dir())
    except TrialError:
        source = _inside(path, trash_dir())
        trial_dir().mkdir(parents=True, exist_ok=True)
        target = _free_name(trial_dir(), source.name)
        with FILES_LOCK:
            shutil.move(str(source), str(target))
        conn.execute("UPDATE trial_tracks SET path=? WHERE deezer_id=? AND state=?", (str(target), str(deezer_id), TRASH))
        metadata_fix.move_file(conn, holder["path"], target)
        path = target
    conn.execute(
        "INSERT INTO trial_tracks(deezer_id, track_key, artist, title, album, path, size, mix_id, downloaded_at,"
        " trial_ends_at, state, state_at, account_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(deezer_id), holder["track_key"], holder["artist"], holder["title"], holder["album"], str(path),
         holder["size"], mix_id, int(now), int(now) + TRIAL_DAYS * DAY, ON_TRIAL, int(now), stats_db.checked_account(account)),
    )
    conn.commit()
    return True


def replace_by_library(conn, deezer_id, library_path, now) -> None:
    """The library already has the track (downloaded by hand, say): rather than a
    second copy, every profile's trial ends kept, the playlists and histories use
    the library's file, and the trial copy goes."""
    rows = rows_of(conn, deezer_id)
    holder = _holder(rows)
    if holder is None:
        return
    copy = _inside(holder["path"], trial_dir(), trash_dir())
    for row in rows:
        if row["state"] in ACTIVE:
            _set(conn, deezer_id, row["account_id"], KEPT, now, "Also in your library", library_path)
        elif row["state"] == TRASH:
            _set(conn, deezer_id, row["account_id"], DELETED, now, row["reason"])
    _follow_move(holder["path"], library_path)
    with FILES_LOCK:
        copy.unlink(missing_ok=True)


def keep(conn, deezer_id, account, now, reason="Kept by hand") -> None:
    """Into the library, for every profile: it is the same disk."""
    row = get(conn, deezer_id, account)
    if row is None or row["state"] not in ACTIVE:
        raise TrialError("This track is not waiting for a decision")
    source = _inside(row["path"], trial_dir())
    target = _to_library(conn, deezer_id, source, now, account)
    _set(conn, deezer_id, account, KEPT, now, reason, target)
    metadata_fix.move_file(conn, row["path"], target)
    _follow_move(row["path"], target)


def remove(conn, deezer_id, account, now, reason="Removed") -> None:
    """Turned down by this profile. The file goes to the trash only once no other
    profile has it on trial, and never while another's playlist uses it."""
    row = get(conn, deezer_id, account)
    if row is None or row["state"] not in ACTIVE:
        raise TrialError("This track is not waiting for a decision")
    _inside(row["path"], trial_dir())
    _set(conn, deezer_id, account, TRASH, now, reason)
    if _keep_for_others(conn, row, account, now):
        return
    if _still_on_trial(conn, deezer_id):
        _drop_from_generated(row["path"], account)
        return
    _settle(conn, deezer_id, now, row["path"])


def delete_now(conn, deezer_id, account, now, reason) -> None:
    """End of the trial with Delete permanently on: no trash for this profile.
    The file stays while another profile has it on trial or in its trash."""
    row = get(conn, deezer_id, account)
    if row is None or row["state"] not in ACTIVE:
        raise TrialError("This track is not waiting for a decision")
    _inside(row["path"], trial_dir())
    _set(conn, deezer_id, account, DELETED, now, reason)
    if _keep_for_others(conn, row, account, now):
        return
    if _still_on_trial(conn, deezer_id):
        _drop_from_generated(row["path"], account)
        return
    _settle(conn, deezer_id, now, row["path"])


def keep_all_pending(conn, account, now, deezer_ids) -> int:
    """The tracks shown under To review, kept in one go."""
    count = 0
    for deezer_id in deezer_ids:
        row = get(conn, deezer_id, account)
        if row is None or row["state"] != PENDING:
            continue
        try:
            keep(conn, deezer_id, account, now)
            count += 1
        except (TrialError, OSError) as e:
            logger.warning("Could not keep %s: %s", deezer_id, e)
    return count


def remove_all_pending(conn, account, now) -> int:
    count = 0
    for row in conn.execute("SELECT deezer_id FROM trial_tracks WHERE state=? AND account_id=?", (PENDING, account)).fetchall():
        try:
            remove(conn, row["deezer_id"], account, now)
            count += 1
        except (TrialError, OSError) as e:
            logger.warning("Could not remove %s: %s", row["deezer_id"], e)
    return count


def restore(conn, deezer_id, account, now) -> None:
    """Taking a track back out of the trash is a decision to keep it: into the
    library, for everyone. Its file may still be in the trial folder, when
    another profile had it on trial."""
    row = get(conn, deezer_id, account)
    if row is None or row["state"] != TRASH:
        raise TrialError("This track is not in the trash")
    source = _inside(row["path"], trash_dir(), trial_dir())
    target = _to_library(conn, deezer_id, source, now, account)
    _set(conn, deezer_id, account, KEPT, now, "Restored", target)
    metadata_fix.move_file(conn, row["path"], target)
    _follow_move(row["path"], target)


def purge(conn, account, now, trash_days=TRASH_DAYS) -> int:
    """What is in this account's trash, after its days there."""
    limit = int(now) - trash_days * DAY
    rows = conn.execute("SELECT * FROM trial_tracks WHERE state=? AND state_at<=? AND account_id=?",
                        (TRASH, limit, account)).fetchall()
    return _delete_from_trash(conn, rows, now)


def empty_trash(conn, account, now) -> int:
    rows = conn.execute("SELECT * FROM trial_tracks WHERE state=? AND account_id=?", (TRASH, account)).fetchall()
    return _delete_from_trash(conn, rows, now)


def _delete_from_trash(conn, rows, now) -> int:
    """This profile is done waiting: the file goes once no other profile needs it."""
    count = 0
    for row in rows:
        try:
            _set(conn, row["deezer_id"], row["account_id"], DELETED, now, row["reason"])
            _settle(conn, row["deezer_id"], now, row["path"])
        except (TrialError, OSError) as e:
            logger.warning("Could not purge %s: %s", row["deezer_id"], e)
            continue
        count += 1
    return count


def _plays_text(count) -> str:
    return "Never played" if not count else "Played once" if count == 1 else f"Played {count} times"


def _earned(row, plays, mark, used_paths, owned_keys, rules):
    """Why this track has earned its place, or None."""
    played = plays.get(row["deezer_id"], 0)
    if row["path"] in used_paths:
        owners = used_paths[row["path"]] if isinstance(used_paths, dict) else set()
        if not owners or row["account_id"] in owners:
            return "In one of your playlists"
        return f"In a playlist of {', '.join(sorted(label(a) for a in owners))}"
    if row["track_key"] in owned_keys:
        return "Also in your library"
    if played >= rules.plays_needed:
        return _plays_text(played)
    if rules.marks_count and mark.get("starred"):
        return "Starred in Navidrome"
    if rules.marks_count and (mark.get("rating") or 0) >= KEEP_RATING:
        return f"Rated {mark['rating']} in Navidrome"
    return None


def _end_trial(conn, row, now, reason, rules, report) -> None:
    try:
        if rules.delete_at_end:
            delete_now(conn, row["deezer_id"], row["account_id"], now, reason)
            report["deleted"] += 1
        else:
            remove(conn, row["deezer_id"], row["account_id"], now, reason)
            report["trashed"] += 1
    except (TrialError, OSError) as e:
        logger.warning("Could not end the trial of %s: %s", row["deezer_id"], e)


def evaluate(conn, account, plays, marks, used_paths, owned_keys, now, rules=Rules(), migrate=False) -> dict:
    """The regular pass over one account's quarantine, with its owner's signals.
    plays: deezer id -> plays since download. marks: deezer id -> Navidrome's
    star and rating. used_paths: files regular playlists rely on, whoever's.
    owned_keys: tracks you also have outside the quarantine, with their file when
    known (a dict), in which case the trial copy gives way to it. migrate: To
    review still holds tracks whose trial failed under the rules before 1.15."""
    report = {"kept": 0, "review": 0, "trashed": 0, "deleted": 0, "gone": 0}
    rows = conn.execute("SELECT * FROM trial_tracks WHERE state IN (?, ?) AND account_id=?",
                        (ON_TRIAL, PENDING, account)).fetchall()
    for row in rows:
        deezer_id = row["deezer_id"]
        if not Path(row["path"]).exists():
            _set(conn, deezer_id, account, GONE, now, "The file is gone")
            report["gone"] += 1
            continue
        if not rules.auto:
            continue
        # The library has it already: no second copy (core/mix_builder.py gives its file).
        library = owned_keys.get(row["track_key"]) if isinstance(owned_keys, dict) else None
        if library:
            try:
                replace_by_library(conn, deezer_id, library, now)
                report["kept"] += 1
            except (TrialError, OSError) as e:
                logger.warning("Could not replace %s by the library's copy: %s", deezer_id, e)
            continue
        mark = marks.get(deezer_id) or {}
        reason = _earned(row, plays, mark, used_paths, owned_keys, rules)
        if reason and rules.bypass:
            try:
                keep(conn, deezer_id, account, now, reason)
                report["kept"] += 1
            except (TrialError, OSError) as e:
                logger.warning("Could not keep %s: %s", deezer_id, e)
            continue
        if reason:
            if row["state"] == ON_TRIAL or migrate:
                _set(conn, deezer_id, account, PENDING, now, reason)
                report["review"] += row["state"] == ON_TRIAL
            continue
        # Validated once, it waits for you: a stricter rule later does not take it back.
        if row["state"] == PENDING and not migrate:
            continue
        rating = mark.get("rating") or 0
        if rules.marks_count and 0 < rating <= BAD_RATING:
            _end_trial(conn, row, now, f"Rated {rating} in Navidrome", rules, report)
        elif now >= trial_ends_at(row, rules) or row["state"] == PENDING:
            _end_trial(conn, row, now, _plays_text(plays.get(deezer_id, 0)), rules, report)
    return report


def rejected(conn, account) -> dict:
    """What must never be proposed to this account again."""
    rows = conn.execute("SELECT deezer_id, track_key FROM trial_tracks WHERE state IN (?, ?) AND account_id=?",
                        (TRASH, DELETED, account)).fetchall()
    return {"ids": {r["deezer_id"] for r in rows}, "keys": {r["track_key"] for r in rows}}


def active(conn, account) -> list:
    """The tracks of this account's quarantine waiting for a verdict; None for
    everyone's (the disk limits are the same for all)."""
    if account is None:
        return conn.execute("SELECT * FROM trial_tracks WHERE state IN (?, ?) ORDER BY downloaded_at DESC",
                            (ON_TRIAL, PENDING)).fetchall()
    return conn.execute("SELECT * FROM trial_tracks WHERE state IN (?, ?) AND account_id=? ORDER BY downloaded_at DESC",
                        (ON_TRIAL, PENDING, account)).fetchall()


def listing(conn, state, account) -> list:
    return conn.execute("SELECT * FROM trial_tracks WHERE state=? AND account_id=? ORDER BY state_at DESC",
                        (state, account)).fetchall()


def owners(conn) -> list:
    """The accounts with tracks waiting for a verdict or in the trash."""
    return [row[0] for row in conn.execute(
        "SELECT DISTINCT account_id FROM trial_tracks WHERE state IN (?, ?, ?) ORDER BY account_id", (ON_TRIAL, PENDING, TRASH))]


def plays_of_everyone(conn) -> dict:
    """deezer id -> plays since download, every track counted in its owner's
    history: for the disk limits, which every profile shares."""
    found = {}
    for account in {row["account_id"] for row in active(conn, None)}:
        if not stats_db.has_history(account):
            continue
        stats = stats_db.connect(account)
        try:
            for deezer_id, count in plays_since_download(conn, stats, account).items():
                found[deezer_id] = found.get(deezer_id, 0) + count
        finally:
            stats.close()
    return found


def plays_since_download(conn, stats_conn, account) -> dict:
    """deezer id -> plays since the track arrived, found by the key its plays
    carry in its owner's history (stats_conn)."""
    found = {}
    for row in active(conn, account):
        count = stats_conn.execute(
            "SELECT COUNT(*) FROM plays p JOIN tracks t ON t.id = p.track_id WHERE t.key=? AND p.listened_at>=?",
            (row["track_key"], row["downloaded_at"]),
        ).fetchone()[0]
        if count:
            found[row["deezer_id"]] = count
    return found


_marks_cache = {}
_marks_lock = threading.Lock()


def _read_annotations(source) -> tuple:
    """({user id: name}, [(user id, path, starred, rating)]) of every file a
    Navidrome user marked, from a copy."""
    import sqlite3

    from core import stats_import

    with tempfile.TemporaryDirectory(dir=config.DATA_DIR) as folder:
        nd = stats_import._open_copy(source, Path(folder), "navidrome.db",
                                     {"media_file": {"id", "path"}, "annotation": {"item_id", "starred", "rating", "user_id"}},
                                     "Navidrome")
        try:
            try:
                users = {r["id"]: r["user_name"] or "" for r in nd.execute('SELECT id, user_name FROM "user"')}
            except sqlite3.DatabaseError:
                users = {}
            rows = [(r["user_id"], r["path"], r["starred"], r["rating"]) for r in nd.execute(
                "SELECT a.user_id, m.path, a.starred, a.rating FROM annotation a"
                " JOIN media_file m ON m.id = a.item_id WHERE a.item_type='media_file'"
            )]
            return users, rows
        finally:
            nd.close()


def _user_of(account, users, rows):
    """The Navidrome user whose stars decide for this account: the one its test
    found, else the one with its user name. When Navidrome has a single user,
    or a single user ever marked anything, those marks are the install's."""
    from core import nd_accounts

    profile = nd_accounts.get(account) or {}
    if profile.get("navidrome_user_id") in users:
        return profile["navidrome_user_id"]
    name = (profile.get("username") or "").strip().casefold()
    for user_id, user_name in users.items():
        if name and user_name.casefold() == name:
            return user_id
    if account == (nd_accounts.owner_fallback() or stats_db.FIRST_ACCOUNT):
        if len(users) == 1:
            return next(iter(users))
        markers = {row[0] for row in rows}
        if len(markers) == 1:
            return next(iter(markers))
    return None


def navidrome_marks(conn, account, now=None):
    """deezer id -> star and rating its owner gave in Navidrome, for this
    account's quarantine; None when Navidrome's database is not mounted. Another
    user's stars do not count. Copying that database takes a while: it is read
    once an hour at most."""
    from core import stats_import

    source = stats_import._navidrome_path()
    if not source.is_file():
        return None
    now = now if now is not None else time.time()
    with _marks_lock:
        read_at, found = _marks_cache.get(str(source), (None, None))
        if read_at is None or now - read_at >= MARKS_EVERY:
            found = _read_annotations(source)
            _marks_cache[str(source)] = (now, found)
    users, rows = found
    user = _user_of(account, users, rows)
    by_name = {f"trial/{Path(r['path']).name}": r["deezer_id"] for r in active(conn, account)}
    marks = {}
    for user_id, path, starred, rating in rows:
        if user_id != user:
            continue
        parts = Path(path).as_posix().split("/")
        deezer_id = by_name.get("/".join(parts[-2:]))
        if deezer_id:
            marks[deezer_id] = {"starred": bool(starred), "rating": rating or 0}
    return marks


def paths_in_regular_playlists() -> dict:
    """Files the profiles' own playlists rely on -> the profiles whose playlists
    they are. Generated playlists do not protect a track."""
    from core.deezer import accounts_for

    found = {}
    for playlist_id, state in config.load_preview_state().items():
        if str(playlist_id).startswith("auto-") or not isinstance(state, dict):
            continue
        paths = {row["local_path"] for row in state.get("rows") or [] if row.get("local_path")}
        if not paths:
            continue
        owners = set(accounts_for(playlist_id))
        for path in paths:
            found.setdefault(path, set()).update(owners)
    return found


def _playlist_owners(path) -> set:
    return paths_in_regular_playlists().get(str(path), set())


def usage(conn, plays, account=None) -> dict:
    """What the download limits look at, for everyone's quarantine unless an
    account is named: the limits are the same for every profile, as they share
    the disk. A track waiting for a decision still takes space, so it counts in
    the size."""
    files = {}
    for row in active(conn, account):
        files.setdefault(row["deezer_id"], []).append(row)
    # One file, however many profiles have it on trial.
    return {
        "unheard": sum(1 for deezer_id, rows in files.items()
                       if any(r["state"] == ON_TRIAL for r in rows) and not plays.get(deezer_id)),
        "bytes": sum(rows[0]["size"] for rows in files.values()),
    }
