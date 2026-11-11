"""Puts a playlist in Navidrome for each account it belongs to.

Two ways, chosen per account (nd_accounts publish_mode):
- "m3u8": the .m3u8 file Navidrome imports. A file always belongs to
  Navidrome's first admin, so only the account made from the install uses it,
  until it switches (switch_to_api below).
- "api": a playlist created and kept up to date through the Subsonic API, as
  that user. Private, updated in place (same ID in every app), and only ever
  one this app created and remembers: an admin also sees the private
  playlists of others, and those are never touched.

The file is written at once. The Subsonic calls run in a background thread, so
a manual fix or a scan never waits for Navidrome. A Navidrome problem never
raises: it is kept with the publication, shown in the playlist, and tried
again later (retry_pending, from the scheduler)."""
import hashlib
import json
import logging
import threading
import time

from core import config, crypto, mixes_db, navidrome_db, nd_accounts, subsonic

logger = logging.getLogger(__name__)

COMMENT = "Managed by Deezer → Navidrome"
RETRY_AFTER = 600
SYNC_EVERY = 300        # a dashboard opened later than this asks for a new sync
MASS_LOSS = 3           # this many playlists of the app gone at once: Navidrome lost them
_cond = threading.Condition()
_jobs = {}
_busy = [0]
_worker = [None]


# --- Publishing -------------------------------------------------------------------

def _accounts():
    return {a["id"]: a for a in nd_accounts.list_accounts()}


def publish(playlist_id, title, rows, accounts=None, force=False, wait=False):
    """Writes the .m3u8 for an account that uses files, and publishes through the
    API for the others. Returns (m3u8 path or None, report)."""
    from core.deezer import accounts_for, playlist_report, write_playlist_outputs

    known = _accounts()
    members = [a for a in (accounts if accounts is not None else accounts_for(playlist_id)) if a]
    by_file = not known or any(known.get(a, {}).get("publish_mode") == "m3u8" for a in members)
    if by_file:
        path, report = write_playlist_outputs(playlist_id, title, rows)
    else:
        path, report = None, playlist_report(playlist_id, title, rows)
    by_api = [a for a in members if known.get(a, {}).get("publish_mode") == "api"]
    if by_api:
        job = {"title": title, "rows": list(rows), "accounts": by_api, "force": force}
        if wait:
            _run(playlist_id, job)
        else:
            _enqueue(playlist_id, job)
    return path, report


def _enqueue(playlist_id, job) -> None:
    with _cond:
        old = _jobs.get(playlist_id)
        if old:
            job = {**job, "accounts": sorted(set(old["accounts"]) | set(job["accounts"])),
                   "force": job["force"] or old["force"]}
        _jobs[playlist_id] = job
        if _worker[0] is None or not _worker[0].is_alive():
            _worker[0] = threading.Thread(target=_work, daemon=True, name="navidrome-publish")
            _worker[0].start()
        _cond.notify_all()


def _work() -> None:
    while True:
        with _cond:
            while not _jobs:
                _cond.wait()
            playlist_id = next(iter(_jobs))
            job = _jobs.pop(playlist_id)
            _busy[0] += 1
        try:
            _run(playlist_id, job)
        except Exception:
            logger.exception("Publishing %s failed", playlist_id)
        finally:
            with _cond:
                _busy[0] -= 1
                _cond.notify_all()


def flush(timeout=60) -> bool:
    """Waits for the background publications. True when they are all done."""
    deadline = time.time() + timeout
    with _cond:
        while _jobs or _busy[0]:
            left = deadline - time.time()
            if left <= 0:
                return False
            _cond.wait(left)
    return True


def _run(playlist_id, job) -> None:
    for account_id in job["accounts"]:
        publish_api(playlist_id, job["title"], job["rows"], account_id, force=job["force"])


def _row(conn, playlist_id, account_id):
    return conn.execute("SELECT * FROM publications WHERE playlist_id=? AND account_id=?",
                        (playlist_id, account_id)).fetchone()


def _save(conn, playlist_id, account_id, **fields) -> dict:
    current = _row(conn, playlist_id, account_id)
    values = dict(current) if current else {"playlist_id": playlist_id, "account_id": account_id, "navidrome_id": "",
                                            "title": "", "content_hash": "", "song_count": 0, "missing": 0,
                                            "hidden": 0, "published_at": 0, "tried_at": 0, "error": "",
                                            "custom_title": ""}
    values.update(fields)
    columns = ("playlist_id", "account_id", "navidrome_id", "title", "content_hash", "song_count", "missing", "hidden",
               "published_at", "tried_at", "error", "custom_title")
    conn.execute(f"INSERT OR REPLACE INTO publications({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                 tuple(values[k] for k in columns))
    conn.commit()
    return values


def _client(account_id):
    creds = nd_accounts.credentials(account_id)
    if not (creds["url"] and creds["username"] and creds["secret"]):
        raise nd_accounts.AccountError("This account needs its address and password: see Settings → Navidrome accounts.")
    return subsonic.Client(creds["url"], creds["username"], creds["auth_type"], creds["secret"])


def matched_paths(rows) -> list:
    ordered = sorted(rows, key=lambda r: int(r.get("number") or 0))
    return [r["local_path"] for r in ordered if r.get("matched") is True and r.get("local_path")]


def resolve(rows, account, client=None):
    """The Navidrome song IDs of the matched tracks, in order, with how many
    Navidrome does not know yet and how many this user may not see."""
    paths = matched_paths(rows)
    index, rights = navidrome_db.songs()
    if index is None:
        return _search(paths, client)
    hits = [index.get(navidrome_db.norm_path(p)) for p in paths]
    read_at = navidrome_db.songs_read_at() or 0
    if None in hits and time.time() - read_at > navidrome_db.MISS_REFRESH:
        # A song may have been scanned since the last read.
        index, rights = navidrome_db.songs(fresh_after=0)
        if index is not None:
            hits = [index.get(navidrome_db.norm_path(p)) for p in paths]
    user = account.get("navidrome_user_id")
    allowed = rights.get(user, set()) if rights is not None and user else None
    ids, missing, hidden = [], 0, 0
    for hit in hits:
        if hit is None:
            missing += 1
        elif allowed is not None and hit[1] is not None and hit[1] not in allowed:
            hidden += 1
        else:
            ids.append(hit[0])
    return ids, missing, hidden


def _search(paths, client):
    """Without Navidrome's database: each track searched by its tags. Stricter
    than useful: a song with another title, artist or length is left out."""
    from core.library import load_library_cache
    from core.stats_db import name_key, title_key, split_artists

    if client is None or not paths:
        return [], len(paths), 0
    entries = {navidrome_db.norm_path(e.get("path", "")): e for e in load_library_cache(config.get_paths_from_config()[2])}
    ids, missing = [], 0
    for path in paths:
        entry = entries.get(navidrome_db.norm_path(path)) or {}
        title, artists = entry.get("tag_title") or "", split_artists(entry.get("tag_artist") or "")
        if not title or not artists:
            missing += 1
            continue
        try:
            found = (client.call("search3", query=f"{artists[0]} {title}", songCount=20, artistCount=0,
                                 albumCount=0).get("searchResult3") or {}).get("song") or []
        except subsonic.SubsonicError:
            missing += 1
            continue
        duration = entry.get("duration") or 0
        match = next((s for s in found if title_key(s.get("title", "")) == title_key(title)
                      and name_key(artists[0]) in name_key(s.get("artist", ""))
                      and (not duration or not s.get("duration") or abs(float(s["duration"]) - float(duration)) <= 3)), None)
        if match:
            ids.append(str(match["id"]))
        else:
            missing += 1
    return ids, missing, 0


def publish_api(playlist_id, title, rows, account_id, force=False, now=None) -> dict:
    """One playlist for one account, through the Subsonic API. Never raises for
    a Navidrome problem: the result, error included, is kept and returned."""
    now = int(now or time.time())
    conn = mixes_db.connect()
    try:
        current = _row(conn, playlist_id, account_id)
        try:
            client = _client(account_id)
            account = nd_accounts.get(account_id) or {}
        except (nd_accounts.AccountError, crypto.DecryptError) as e:
            message = str(e) if isinstance(e, nd_accounts.AccountError) else "The password of this account must be entered again."
            return _save(conn, playlist_id, account_id, tried_at=now, error=message)
        ids, missing, hidden = resolve(rows, account, client)
        if not ids and (missing or hidden):
            # Not one track found: the path mappings or Navidrome's database are
            # wrong, or the user cannot see the library. Publishing would empty
            # the playlist in Navidrome; it is left as it is.
            reason = ("this Navidrome user cannot see the library of these tracks" if hidden and not missing else
                      "check the path mappings in Settings, and that Navidrome has scanned the library")
            return _save(conn, playlist_id, account_id, navidrome_id=current["navidrome_id"] if current else "",
                         missing=missing, hidden=hidden, tried_at=now,
                         error=f"None of the {missing + hidden} tracks was found in Navidrome: {reason}.")
        digest = hashlib.sha1(json.dumps([title, ids]).encode()).hexdigest()
        navidrome_id = current["navidrome_id"] if current else ""
        if current and navidrome_id and current["content_hash"] == digest and not current["error"] and not force:
            return _save(conn, playlist_id, account_id, missing=missing, hidden=hidden, tried_at=now)
        try:
            if navidrome_id:
                try:
                    # With playlistId, createPlaylist replaces the songs and keeps the ID.
                    client.call("createPlaylist", playlistId=navidrome_id, songId=ids)
                    # A name given in Navidrome is kept: only the app's own name follows Deezer.
                    if not current["custom_title"] and current["title"] != title:
                        client.call("updatePlaylist", playlistId=navidrome_id, name=title)
                except subsonic.SubsonicError as e:
                    # "Not found" is also what a song ID gone stale says: only a
                    # playlist Navidrome no longer has was deleted by its user.
                    if e.code != 70 or not _really_gone(client, navidrome_id):
                        raise
                    # Deleted in Navidrome by its user: it leaves this account.
                    conn.close()
                    deleted_in_navidrome(playlist_id, account_id)
                    return {"deleted": True, "error": ""}
            if not navidrome_id:
                created = client.call("createPlaylist", name=title, songId=ids)
                navidrome_id = str((created.get("playlist") or {}).get("id") or "")
                if not navidrome_id:
                    raise subsonic.SubsonicError(0, "Navidrome did not say which playlist it made.")
                client.call("updatePlaylist", playlistId=navidrome_id, comment=COMMENT, public="false")
        except subsonic.SubsonicError as e:
            return _save(conn, playlist_id, account_id, navidrome_id=navidrome_id, missing=missing, hidden=hidden,
                         tried_at=now, error=e.message)
        return _save(conn, playlist_id, account_id, navidrome_id=navidrome_id, title=title, content_hash=digest,
                     song_count=len(ids), missing=missing, hidden=hidden, published_at=now, tried_at=now, error="")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def unpublish(playlist_id, accounts=None) -> None:
    """Removes the playlist this app made in Navidrome, for these accounts (all
    by default). The .m3u8 files are the callers' business."""
    conn = mixes_db.connect()
    try:
        rows = conn.execute("SELECT * FROM publications WHERE playlist_id=?", (playlist_id,)).fetchall()
        for row in rows:
            if accounts is not None and row["account_id"] not in accounts:
                continue
            if row["navidrome_id"]:
                try:
                    _client(row["account_id"]).call("deletePlaylist", id=row["navidrome_id"])
                except subsonic.SubsonicError as e:
                    if e.code != 70:
                        _save(conn, playlist_id, row["account_id"], tried_at=int(time.time()),
                              error=f"Could not remove it from Navidrome: {e.message}")
                        continue
                except (nd_accounts.AccountError, crypto.DecryptError):
                    pass
            conn.execute("DELETE FROM publications WHERE playlist_id=? AND account_id=?", (playlist_id, row["account_id"]))
            conn.commit()
    finally:
        conn.close()


def remove_file(playlist_id, title):
    """The .m3u8 of a playlist, with its report and list of missing tracks: only
    these three files, then their folder if it is empty. Returns the .m3u8 path
    as it was, or None when there was none."""
    from core.deezer import playlist_folder_name

    name = playlist_folder_name(playlist_id, title)
    folder = config.get_paths_from_config()[1] / name
    playlist_file = folder / f"{name}.m3u8"
    existed = playlist_file.exists()
    for file in (f"{name}.m3u8", "report.json", "missing.txt"):
        (folder / file).unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    return playlist_file if existed else None


def _delete_imported(account_id, playlist_file) -> bool:
    """Navidrome keeps a playlist it imported even once its file is gone: the
    copy is removed through the API, when this account can sign in and
    Navidrome's database says which one it is."""
    path = _navidrome_path(playlist_file)
    folder = _navidrome_path(config.get_paths_from_config()[1])
    if not path or not folder:
        return False
    try:
        client = _client(account_id)
    except (nd_accounts.AccountError, crypto.DecryptError):
        return False
    removed = False
    for copy in navidrome_db.file_playlists(folder) or []:
        if copy["path"].replace("\\", "/") == path:
            try:
                client.call("deletePlaylist", id=copy["id"])
                removed = True
            except subsonic.SubsonicError as e:
                logger.warning("Could not remove the copy Navidrome imported from %s: %s", path, e.message)
    return removed


def forget_account(account_id) -> dict:
    """A Navidrome account about to be removed: every playlist leaves it in
    Navidrome, while its password is still known. One only it had, its
    generated playlists among them, leaves the app too; the others stay for
    their other accounts. {"left": n, "removed": n}."""
    from core.deezer import accounts_for, load_playlists, remove_entries, set_accounts

    left, removed = 0, []
    for playlist in load_playlists():
        members = accounts_for(playlist["id"])
        if account_id not in members:
            continue
        try:
            remove_from(playlist["id"], playlist["title"], [account_id])
        except Exception as e:
            logger.warning("Could not remove %s from %s in Navidrome: %s", playlist["id"], account_id, e)
        others = [a for a in members if a != account_id]
        if others:
            set_accounts(playlist["id"], others)
            left += 1
        else:
            removed.append(playlist["id"])
    if removed:
        remove_entries(removed)
        for playlist_id in removed:
            config.delete_playlist_cache(playlist_id)
    conn = mixes_db.connect()
    try:
        conn.execute("DELETE FROM publications WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM navidrome_playlists WHERE account_id=?", (account_id,))
        conn.execute("DELETE FROM meta WHERE key=?", (f"sync:{account_id}",))
        conn.commit()
    finally:
        conn.close()
    return {"left": left, "removed": len(removed)}


def remove_from(playlist_id, title, accounts) -> bool:
    """The playlist leaves these accounts in Navidrome: for the account that uses
    files, its .m3u8 and the copy Navidrome imported from it; for the others,
    the playlist made through the API. False when an imported copy may still be
    in Navidrome."""
    known = _accounts()
    complete = True
    file_accounts = [a for a in accounts if known.get(a, {}).get("publish_mode") == "m3u8"]
    # As publish(): with no account at all, the playlist was written as a file.
    if file_accounts or not known:
        playlist_file = remove_file(playlist_id, title)
        if playlist_file is not None and file_accounts:
            complete = any(_delete_imported(a, playlist_file) for a in file_accounts)
    unpublish(playlist_id, [a for a in accounts if known.get(a, {}).get("publish_mode") == "api"])
    return complete


def retry_pending(now=None) -> int:
    """Publications with songs Navidrome did not know yet, or that failed, are
    tried again from the saved tracks of the playlist."""
    from core.deezer import accounts_for, playlist_title

    now = int(now or time.time())
    conn = mixes_db.connect()
    try:
        rows = conn.execute("SELECT * FROM publications WHERE (missing > 0 OR error != '') AND tried_at <= ?",
                            (now - RETRY_AFTER,)).fetchall()
    finally:
        conn.close()
    queued = 0
    for row in rows:
        if row["account_id"] not in accounts_for(row["playlist_id"]):
            continue
        state = config.get_preview_state(row["playlist_id"]) or {}
        if not isinstance(state.get("rows"), list):
            continue
        title = state.get("playlist_title") or playlist_title(row["playlist_id"])
        _enqueue(row["playlist_id"], {"title": title, "rows": state["rows"], "accounts": [row["account_id"]],
                                      "force": False})
        queued += 1
    return queued


# --- Following what happens in Navidrome ---------------------------------------------

_sync_locks = {}
_sync_guard = threading.Lock()


def deleted_in_navidrome(playlist_id, account_id) -> str:
    """Its user deleted the playlist in Navidrome: it leaves this account. With no
    account left, it leaves the app, as with Delete. Returns its title."""
    from core.deezer import accounts_for, playlist_title, remove_entries, set_accounts

    title = playlist_title(playlist_id)
    remaining = [a for a in accounts_for(playlist_id) if a != account_id]
    conn = mixes_db.connect()
    try:
        conn.execute("DELETE FROM publications WHERE playlist_id=? AND account_id=?", (playlist_id, account_id))
        conn.commit()
    finally:
        conn.close()
    if remaining:
        set_accounts(playlist_id, remaining)
    else:
        remove_entries([playlist_id])
        config.delete_playlist_cache(playlist_id)
    logger.info("Playlist %s deleted in Navidrome by %s: removed from it", title, account_id)
    return title


def _really_gone(client, navidrome_id) -> bool:
    """True only when Navidrome says it has no such playlist. Any other answer,
    or none, is not proof enough to take the playlist away from the app."""
    try:
        client.call("getPlaylist", id=navidrome_id)
    except subsonic.SubsonicError as e:
        return e.code == 70
    return False


def _listed(client) -> list:
    found = (client.call("getPlaylists").get("playlists") or {}).get("playlist") or []
    return found if isinstance(found, list) else [found]


def _app_file_ids(account) -> set:
    """Playlists Navidrome imported from the .m3u8 files of this app: they are
    the app's, not made by hand."""
    folder = _navidrome_path(config.get_paths_from_config()[1])
    return {p["id"] for p in (navidrome_db.file_playlists(folder) or [])} if folder else set()


def sync_account(account_id, now=None):
    """Brings back what the user did in Navidrome: a playlist of the app deleted
    there leaves this account, a new name given there is kept, and the playlists
    made by hand are listed. Returns the report, also kept for Settings; None
    when the account cannot sign in."""
    now = int(now or time.time())
    account = nd_accounts.get(account_id)
    if account is None:
        return None
    try:
        client = _client(account_id)
    except (nd_accounts.AccountError, crypto.DecryptError):
        return None
    report = {"at": now, "removed": [], "renamed": 0, "republished": 0, "handmade": 0, "warning": "", "error": ""}
    try:
        listed = _listed(client)
    except subsonic.SubsonicError as e:
        report["error"] = e.message
        _keep_report(account_id, report)
        return report
    user = account["username"].lower()
    mine = {str(p.get("id")): p for p in listed if str(p.get("owner") or "").lower() == user}
    conn = mixes_db.connect()
    try:
        publications = [dict(r) for r in conn.execute(
            "SELECT * FROM publications WHERE account_id=? AND navidrome_id != ''", (account_id,))]
    finally:
        conn.close()
    if account["publish_mode"] == "api":
        gone = [p for p in publications if p["navidrome_id"] not in mine]
        if len(publications) >= MASS_LOSS and len(gone) == len(publications):
            # Every one at once: Navidrome was reset or restored, the user did not
            # delete them all. They are made again rather than taken away.
            conn = mixes_db.connect()
            try:
                conn.execute("UPDATE publications SET navidrome_id='', content_hash='' WHERE account_id=?", (account_id,))
                conn.commit()
            finally:
                conn.close()
            for publication in gone:
                state = config.get_preview_state(publication["playlist_id"]) or {}
                if isinstance(state.get("rows"), list):
                    _enqueue(publication["playlist_id"], {"title": state.get("playlist_title") or publication["title"],
                                                          "rows": state["rows"], "accounts": [account_id], "force": True})
            report["republished"] = len(gone)
            report["warning"] = (f"Navidrome no longer had any of the {len(gone)} playlists made for this user: "
                                 "they are published again.")
        else:
            for publication in gone:
                # Missing from the list may be a list that is wrong (an owner
                # renamed, a server restored): asked about each one first.
                if _really_gone(client, publication["navidrome_id"]):
                    report["removed"].append(deleted_in_navidrome(publication["playlist_id"], account_id))
            conn = mixes_db.connect()
            try:
                for publication in publications:
                    listed_playlist = mine.get(publication["navidrome_id"])
                    if not listed_playlist:
                        continue
                    name = str(listed_playlist.get("name") or "")
                    custom = "" if name == publication["title"] else name
                    if custom != publication["custom_title"]:
                        conn.execute("UPDATE publications SET custom_title=? WHERE playlist_id=? AND account_id=?",
                                     (custom, publication["playlist_id"], account_id))
                conn.commit()
                report["renamed"] = conn.execute(
                    "SELECT COUNT(*) FROM publications WHERE account_id=? AND custom_title != ''", (account_id,)).fetchone()[0]
            finally:
                conn.close()
    ours = {p["navidrome_id"] for p in publications}
    app_files = _app_file_ids(account)
    handmade = [p for pid, p in mine.items()
                if pid not in ours and pid not in app_files and (p.get("comment") or "") != COMMENT]
    conn = mixes_db.connect()
    try:
        conn.execute("DELETE FROM navidrome_playlists WHERE account_id=?", (account_id,))
        conn.executemany(
            "INSERT INTO navidrome_playlists(account_id, navidrome_id, name, song_count, duration, cover_art, changed,"
            " synced_at) VALUES (?,?,?,?,?,?,?,?)",
            [(account_id, str(p.get("id")), str(p.get("name") or ""), int(p.get("songCount") or 0),
              int(p.get("duration") or 0), str(p.get("coverArt") or ""), str(p.get("changed") or ""), now)
             for p in handmade])
        conn.commit()
    finally:
        conn.close()
    report["handmade"] = len(handmade)
    _keep_report(account_id, report)
    return report


def _keep_report(account_id, report) -> None:
    conn = mixes_db.connect()
    try:
        mixes_db.set_meta(conn, f"sync:{account_id}", report)
    finally:
        conn.close()


def sync_report(account_id):
    conn = mixes_db.connect()
    try:
        return mixes_db.get_meta(conn, f"sync:{account_id}")
    finally:
        conn.close()


def sync_all(now=None) -> int:
    """Every account that can sign in. From the scheduler."""
    done = 0
    for account in nd_accounts.list_accounts():
        if nd_accounts.public(account)["complete"]:
            try:
                if sync_account(account["id"], now) is not None:
                    done += 1
            except Exception:
                logger.exception("Could not sync %s with Navidrome", account["id"])
    return done


def sync_soon(account_id) -> bool:
    """A dashboard opened: the account is synced in the background when its last
    sync is old. True when one was started."""
    report = sync_report(account_id) or {}
    if time.time() - int(report.get("at") or 0) < SYNC_EVERY:
        return False
    account = nd_accounts.get(account_id)
    if account is None or not nd_accounts.public(account)["complete"]:
        return False
    with _sync_guard:
        lock = _sync_locks.setdefault(account_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return False

    def run():
        try:
            sync_account(account_id)
        except Exception:
            logger.exception("Could not sync %s with Navidrome", account_id)
        finally:
            lock.release()

    threading.Thread(target=run, daemon=True, name=f"navidrome-sync-{account_id}").start()
    return True


def custom_titles(account_id) -> dict:
    """playlist ID -> the name its user gave it in Navidrome."""
    conn = mixes_db.connect()
    try:
        return {r["playlist_id"]: r["custom_title"] for r in conn.execute(
            "SELECT playlist_id, custom_title FROM publications WHERE account_id=? AND custom_title != ''", (account_id,))}
    finally:
        conn.close()


def handmade(account_id) -> list:
    """The playlists this user made in Navidrome, as of the last sync."""
    conn = mixes_db.connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM navidrome_playlists WHERE account_id=? ORDER BY name COLLATE NOCASE", (account_id,))]
    finally:
        conn.close()


# --- Switching an account from files to the API -----------------------------------

class SwitchError(Exception):
    """Shown as it is: nothing was changed."""


def _our_files(account_id):
    """The playlists of this account, with their .m3u8 when it exists."""
    from core.deezer import load_playlists, playlist_folder_name

    base = config.get_paths_from_config()[1]
    found = []
    for playlist in load_playlists():
        if account_id not in playlist.get("accounts", []):
            continue
        name = playlist_folder_name(playlist["id"], playlist["title"])
        file = base / name / f"{name}.m3u8"
        found.append({"id": playlist["id"], "title": playlist["title"], "file": file if file.exists() else None})
    return found


def _navidrome_path(path):
    from core.deezer import map_host_path_to_navidrome

    try:
        return map_host_path_to_navidrome(path, config.get_paths_from_config()[3]).as_posix()
    except ValueError:
        return None


def _imported_from(playlists):
    """Playlists Navidrome imported from these .m3u8 files, from its database:
    (list, whether the database could be read)."""
    folder = _navidrome_path(config.get_paths_from_config()[1])
    imported = navidrome_db.file_playlists(folder) if folder else None
    ours = {_navidrome_path(p["file"]) for p in playlists if p["file"]}
    return [p for p in imported or [] if p["path"].replace("\\", "/") in ours], imported is not None


def switch_preview(account_id) -> dict:
    """What switching this account to the API would do, without doing it."""
    account = nd_accounts.get(account_id)
    if account is None:
        raise SwitchError("Unknown Navidrome account.")
    problems = []
    if account["publish_mode"] != "m3u8":
        problems.append("Its playlists already go to Navidrome as this user.")
    elif not nd_accounts.public(account)["complete"]:
        problems.append("Add its address and password first.")
    elif not (account.get("last_test") or {}).get("ok"):
        problems.append("Test its connection first.")
    playlists = _our_files(account_id)
    old, database = _imported_from(playlists)
    test = account.get("last_test") or {}
    removable = bool(test.get("admin")) or all(p["owner_id"] == account.get("navidrome_user_id") for p in old)
    return {"ok": not problems, "problems": problems, "playlists": len(playlists),
            "files": sum(1 for p in playlists if p["file"]), "database": database,
            "old": [{"name": p["name"], "owner": p["owner"]} for p in old], "can_remove_old": removable}


def switch_to_api(account_id, progress=None) -> dict:
    """Publishes every playlist of this account through the API, then removes
    its .m3u8 files and the playlists Navidrome had imported from them. If a
    playlist cannot be published, what was made is undone and nothing else
    changes."""
    from core.deezer import playlist_title

    emit = progress or (lambda message, percent=None: None)
    preview = switch_preview(account_id)
    if not preview["ok"]:
        raise SwitchError(" ".join(preview["problems"]))
    playlists = _our_files(account_id)
    old, database = _imported_from(playlists)
    made, failed = [], []
    for done, playlist in enumerate(playlists, start=1):
        state = config.get_preview_state(playlist["id"]) or {}
        rows = state.get("rows") if isinstance(state.get("rows"), list) else None
        if rows is None:
            continue
        emit(f"Publishing {playlist['title']}", round(done / max(1, len(playlists)) * 70))
        result = publish_api(playlist["id"], state.get("playlist_title") or playlist_title(playlist["id"]), rows,
                             account_id, force=True)
        (failed if result.get("error") else made).append((playlist, result))
    if failed:
        for playlist, _ in made:
            unpublish(playlist["id"], [account_id])
        first_playlist, first_result = failed[0]
        raise SwitchError(f"Navidrome refused {len(failed)} playlist(s), for example {first_playlist['title']}: "
                          f"{first_result['error']} Nothing was changed.")
    nd_accounts.set_publish_mode(account_id, "api")
    emit("Removing the .m3u8 files", 80)
    removed_files = 0
    for playlist in playlists:
        if playlist["file"]:
            remove_file(playlist["id"], playlist["title"])
            removed_files += 1
    emit("Removing the copies Navidrome imported from them", 90)
    deleted, left = 0, []
    client = _client(account_id)
    for copy in old:
        try:
            client.call("deletePlaylist", id=copy["id"])
            deleted += 1
        except subsonic.SubsonicError:
            left.append(copy["name"])
    return {"published": len(made), "files_removed": removed_files, "old_removed": deleted, "old_left": left,
            "database": database}


def status(playlist_id) -> dict:
    """What the playlist drawer shows: each account, whether the playlist is in
    it, and how it was last published there."""
    from core.deezer import accounts_for

    members = accounts_for(playlist_id)
    conn = mixes_db.connect()
    try:
        publications = {r["account_id"]: dict(r) for r in
                        conn.execute("SELECT * FROM publications WHERE playlist_id=?", (playlist_id,))}
    finally:
        conn.close()
    accounts = []
    for account in nd_accounts.list_accounts():
        public = nd_accounts.public(account)
        pub = publications.get(account["id"])
        accounts.append({"id": account["id"], "label": account["label"], "member": account["id"] in members,
                         "mode": account["publish_mode"], "complete": public["complete"],
                         "publication": {k: pub[k] for k in ("song_count", "missing", "hidden", "published_at",
                                                             "tried_at", "error", "custom_title")}
                         | {"in_navidrome": bool(pub["navidrome_id"])} if pub else None})
    return {"accounts": accounts}
