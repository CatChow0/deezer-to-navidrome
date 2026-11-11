import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from core.config import (
    COVERS_DIR,
    PLAYLIST_IDS_FILE,
    ensure_dirs,
    get_paths_from_config,
    get_preview_state,
    load_config,
    modify_preview_state,
)
from core.library import load_library_cache, rebuild_library_cache_full_with_progress
from core.normalization import extract_version_flags, normalize_text
from core.matching import build_title_index, find_best_match
from core import files
from core.utils import sanitize_filename


# Mixes from a Deezer account are followed like playlists, under IDs such as
# "mix-stl-inspired-by-1" (smart tracklist) or "mix-flow-chill" (Flow mood).
# Those of another account than dz1 carry it ("mix-dz2-flow-chill"): two
# accounts each have their own Flow.
MIX_ID = re.compile(r"^mix-(?:(dz[1-9][0-9]*)-)?(stl|flow)-([a-z0-9_-]+)$")
FIRST_DEEZER_ACCOUNT = "dz1"


def mix_id(kind: str, source_id: str, deezer_account=None) -> str:
    prefix = f"{deezer_account}-" if deezer_account and deezer_account != FIRST_DEEZER_ACCOUNT else ""
    return f"mix-{prefix}{kind}-{re.sub(r'[^a-z0-9_-]+', '-', str(source_id).lower())}"


def parse_mix_id(playlist_id: str):
    m = MIX_ID.match(str(playlist_id))
    return (m.group(2), m.group(3)) if m else None


def mix_deezer_account(playlist_id: str):
    """The Deezer account whose mix it is."""
    m = MIX_ID.match(str(playlist_id))
    return (m.group(1) or FIRST_DEEZER_ACCOUNT) if m else None


def parse_xp_id(playlist_id: str):
    """("spotify"|"csv", source id) for a playlist imported from another platform."""
    from core.crossplatform import parse_xp_id as parse

    return parse(playlist_id)


# Playlists this app generates from your listening (core/mix_builder.py), one set
# per Navidrome account: "auto-daily-1" for the account made from the install,
# as before profiles, and "auto-nd2-daily-1" for the others.
AUTO_ID = re.compile(r"^auto-(?:(nd[1-9][0-9]*)-)?(?:(daily|blend)-([1-9])|(discover|trial))$")
FIRST_NAVIDROME_ACCOUNT = "nd1"


def auto_id(account, name, slot=None) -> str:
    """The ID of a generated playlist ("daily", 2), or without a slot, the name
    its history is kept under."""
    prefix = f"{account}-" if account and account != FIRST_NAVIDROME_ACCOUNT else ""
    return f"auto-{prefix}{name}" + (f"-{slot}" if slot else "")


def parse_auto_id(playlist_id):
    """(account, name, slot) of a generated playlist, or None."""
    m = AUTO_ID.match(str(playlist_id))
    if not m:
        return None
    return m.group(1) or FIRST_NAVIDROME_ACCOUNT, m.group(2) or m.group(4), int(m.group(3)) if m.group(3) else None


def is_auto_id(playlist_id: str) -> bool:
    return parse_auto_id(playlist_id) is not None


def _valid_playlist_id(pid: str) -> bool:
    return pid.isdigit() or parse_mix_id(pid) is not None or parse_xp_id(pid) is not None or is_auto_id(pid)


def _playlist_sort_key(p):
    # Deezer playlists by ID, then imported ones and mixes by title.
    if pid_is_number(p["id"]):
        return (0, 0, "", int(p["id"]))
    return (1 if parse_mix_id(p["id"]) else 0, 1, p["title"].lower(), 0)


def pid_is_number(pid) -> bool:
    return str(pid).isdigit()


def playlist_kind(pid: str) -> str:
    if parse_mix_id(pid):
        return "mix"
    if parse_xp_id(pid):
        return "xp"
    if is_auto_id(pid):
        return "auto"
    return "playlist"


# Every read-modify-write of the playlists file holds it: a scan, a mix and a
# route saving at once would otherwise each drop what the others added.
_playlists_lock = threading.RLock()


def saved_entries() -> list:
    """The entries of the playlists file as saved, without calling Deezer. The
    format from before 1.6 (a bare list of IDs) gives entries with an ID only."""
    with _playlists_lock:
        data = files.read_json(PLAYLIST_IDS_FILE, {})
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("playlists"), list):
        return [item for item in data["playlists"] if isinstance(item, dict)]
    if isinstance(data.get("playlist_ids"), list):
        return [{"id": str(raw).strip()} for raw in data["playlist_ids"]]
    return []


def _saved_entry(playlist_id) -> dict:
    return next((item for item in saved_entries() if str(item.get("id")) == str(playlist_id)), {})


def modify_playlists(change):
    """`change(entries) -> entries` on the saved entries, under the lock. Returns
    what `change` returned."""
    with _playlists_lock:
        new = change(saved_entries())
        save_playlists(new)
        return new


def add_entry(entry: dict) -> bool:
    """Adds a playlist to the file. False when it is there already."""
    added = []

    def change(entries):
        if any(str(e.get("id")) == str(entry["id"]) for e in entries):
            return entries
        added.append(True)
        return [*entries, entry]

    modify_playlists(change)
    return bool(added)


def remove_entries(playlist_ids) -> None:
    gone = {str(i) for i in playlist_ids}
    modify_playlists(lambda entries: [e for e in entries if str(e.get("id")) not in gone])


def put_entry(entry: dict) -> None:
    """Adds the playlist, or replaces the saved one with the same ID."""
    modify_playlists(lambda entries: [*(e for e in entries if str(e.get("id")) != str(entry["id"])), entry])


def _saved_profiles(playlist_id: str) -> list:
    """The Navidrome profiles a saved playlist belongs to, without calling Deezer."""
    return [str(a) for a in _saved_entry(playlist_id).get("accounts") or [] if a]


def _reading_accounts(playlist_id: str, profiles=None) -> list:
    """The Deezer accounts to read a playlist with: those of its profiles, then
    the default one. A private playlist is readable by its owner's account only."""
    from core import account_context, deezer_accounts

    profiles = _saved_profiles(playlist_id) if profiles is None else profiles
    ids = [account_context.deezer_account_of(p) for p in profiles] + [deezer_accounts.default_id()]
    return [a for i, a in enumerate(ids) if a and a not in ids[:i]]


def _through_accounts(read, playlist_id: str, profiles=None):
    """`read(account)` with the first Deezer account that can, else None."""
    from core.deezer_account import DeezerAccountError

    for account in _reading_accounts(playlist_id, profiles):
        try:
            result = read(account)
        except (DeezerAccountError, requests.RequestException, ValueError):
            continue
        if result:
            return result
    return None


def fetch_deezer_playlist_info(playlist_id: str, profiles=None):
    """A Deezer playlist's title, cover and size. Read with a Deezer account
    first, which sees a private playlist of its own; else the public API."""
    from core import deezer_account

    found = _through_accounts(lambda account: deezer_account.playlist_info(playlist_id, account), playlist_id, profiles)
    if found:
        return found
    url = f"https://api.deezer.com/playlist/{playlist_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return {
        "id": str(playlist_id),
        "title": data.get("title") or f"playlist_{playlist_id}",
        "picture": data.get("picture_xl")
        or data.get("picture_big")
        or data.get("picture_medium")
        or data.get("picture_small")
        or "",
        "track_count": data.get("nb_tracks", 0),
    }


def cache_cover(playlist):
    playlist_id = playlist["id"]
    picture = playlist.get("picture") or ""
    target = COVERS_DIR / f"{playlist_id}.jpg"

    if target.exists():
        return target.name
    if not picture:
        return None

    try:
        r = requests.get(picture, timeout=30)
        r.raise_for_status()
        target.write_bytes(r.content)
        return target.name
    except Exception:
        return None


def stored_accounts() -> dict:
    """playlist ID -> the Navidrome accounts saved for it, read straight from the
    file (load_playlists may call Deezer for a missing title)."""
    found = {}
    for item in saved_entries():
        if isinstance(item.get("accounts"), list) and item["accounts"]:
            found[str(item.get("id", "")).strip()] = [str(a) for a in item["accounts"] if a]
    return found


def accounts_for(playlist_id) -> list:
    """The Navidrome accounts a playlist is published for. Saved before 1.16, it
    belongs to the account made from the install."""
    from core import nd_accounts

    saved = stored_accounts().get(str(playlist_id))
    if saved:
        return saved
    fallback = nd_accounts.owner_fallback()
    return [fallback] if fallback else []


def set_accounts(playlist_id, accounts) -> list:
    """The Navidrome accounts of a saved playlist, replaced. Returns them."""
    accounts = list(dict.fromkeys(str(a) for a in accounts if a))

    def change(entries):
        for entry in entries:
            if str(entry.get("id")) == str(playlist_id):
                entry["accounts"] = accounts
        return entries

    modify_playlists(change)
    return accounts


def give_to_account(playlist_id, account_id) -> bool:
    """Adds an account to a saved playlist. True when it did not have it yet."""
    members = accounts_for(playlist_id)
    if account_id in members:
        return False
    set_accounts(playlist_id, [*members, account_id])
    return True


def save_playlists(playlists):
    with _playlists_lock:
        _save_playlists(playlists)


def _save_playlists(playlists):
    ensure_dirs()
    cleaned = []
    seen = set()
    previous = stored_accounts()
    previous_folders = {str(e.get("id")): e["folder"] for e in saved_entries() if e.get("folder")}
    for item in playlists:
        pid = str(item.get("id", "")).strip()
        if not _valid_playlist_id(pid) or pid in seen:
            continue
        entry = {
            "id": pid,
            "title": str(item.get("title", "")).strip() or "Unknown title",
            "picture": str(item.get("picture", "")).strip(),
        }
        if "auto_scan_enabled" in item:
            entry["auto_scan_enabled"] = bool(item["auto_scan_enabled"])
        if "auto_scan_interval_minutes" in item:
            entry["auto_scan_interval_minutes"] = max(1, int(item.get("auto_scan_interval_minutes") or 1))
        if "auto_download_after_scan" in item:
            entry["auto_download_after_scan"] = bool(item["auto_download_after_scan"])
        if item.get("source"):
            entry["source"] = str(item["source"])
        if item.get("subtitle"):
            entry["subtitle"] = str(item["subtitle"])
        # Its .m3u8 folder, kept once chosen (playlist_folder_name).
        folder = item.get("folder") or previous_folders.get(pid)
        if folder:
            entry["folder"] = str(folder)
        # The Navidrome accounts it belongs to. An entry given without them keeps
        # those already saved, so a refresh of its title cannot lose them.
        accounts = item.get("accounts") if isinstance(item.get("accounts"), list) else previous.get(pid)
        if accounts:
            entry["accounts"] = list(dict.fromkeys(str(a) for a in accounts if a))
        cleaned.append(entry)
        seen.add(pid)

    cleaned.sort(key=_playlist_sort_key)
    files.write_json(PLAYLIST_IDS_FILE, {"playlists": cleaned})


# Playlist ID -> when Deezer last failed to give its title or picture: asked
# again an hour later, not on each of the scheduler's 30-second passes.
_REFRESH_BACKOFF = 3600
_refresh_failed_at = {}


def _missing_details(pid, title, picture):
    """The title and picture of a saved Deezer playlist that lacks one, or None."""
    if (title and picture) or not pid.isdigit():
        return None
    if time.time() - _refresh_failed_at.get(pid, 0) < _REFRESH_BACKOFF:
        return None
    try:
        info = fetch_deezer_playlist_info(pid)
    except Exception:
        _refresh_failed_at[pid] = time.time()
        return None
    if not info.get("picture"):
        _refresh_failed_at[pid] = time.time()
    return {"title": title or info.get("title") or "", "picture": picture or info.get("picture") or ""}


def load_playlists():
    ensure_dirs()
    playlists = []
    refreshed = {}

    for item in saved_entries():
        pid = str(item.get("id", "")).strip()
        if not _valid_playlist_id(pid):
            continue
        title = str(item.get("title", "")).strip()
        picture = str(item.get("picture", "")).strip()
        found = _missing_details(pid, title, picture)
        if found and (found["title"] != title or found["picture"] != picture):
            refreshed[pid] = found
            title, picture = found["title"], found["picture"]
        playlists.append({
            "id": pid,
            "kind": playlist_kind(pid),
            "source": str(item.get("source") or (parse_xp_id(pid) or ("", ""))[0]),
            "subtitle": str(item.get("subtitle") or ""),
            "title": title or ("Unknown title" if pid.isdigit() else "Mix"),
            "picture": picture,
            "auto_scan_enabled": bool(item.get("auto_scan_enabled", False)),
            "auto_scan_interval_minutes": max(1, int(item.get("auto_scan_interval_minutes") or 60)),
            "auto_download_after_scan": bool(item.get("auto_download_after_scan", False)),
            "accounts": [str(a) for a in item.get("accounts") or [] if a],
        })

    playlists = sorted({p["id"]: p for p in playlists}.values(), key=_playlist_sort_key)
    fallback = None
    for p in playlists:
        p.setdefault("kind", "playlist")
        if not p.get("accounts"):
            if fallback is None:
                from core import nd_accounts

                fallback = nd_accounts.owner_fallback() or ""
            p["accounts"] = [fallback] if fallback else []

    if refreshed:
        # Only the details found: the file may have changed since it was read.
        def change(entries):
            for entry in entries:
                entry.update(refreshed.get(str(entry.get("id")), {}))
            return entries

        modify_playlists(change)

    for p in playlists:
        p["cover_cached"] = cache_cover(p)

    return playlists


def playlist_title(playlist_id: str) -> str:
    """Title from the saved playlists file, without calling Deezer."""
    return _saved_entry(playlist_id).get("title") or str(playlist_id)


def fetch_deezer_playlist_tracks(playlist_id: str, refresh=False, full=False, progress=None):
    """(title, tracks) of a playlist. For a playlist imported from another
    platform, `refresh` reads the source again and matches the new tracks to
    Deezer (`full`: every track not picked by hand); without it the saved
    picks are used, with no network call. `progress(done, total, track)`
    follows that matching."""
    if parse_xp_id(playlist_id):
        from core import crossplatform

        if refresh:
            crossplatform.resync(playlist_id, full=full, progress=progress)
        return playlist_title(playlist_id), crossplatform.xp_tracks(playlist_id)

    mix = parse_mix_id(playlist_id)
    if mix:
        from core.deezer_account import mix_tracks

        return playlist_title(playlist_id), mix_tracks(*mix, account=mix_deezer_account(playlist_id))

    from core import deezer_account

    # With a Deezer account: every track in one call, a private playlist of its own too.
    found = _through_accounts(
        lambda account: (deezer_account.playlist_info(playlist_id, account)["title"],
                         deezer_account.playlist_tracks(playlist_id, account)),
        playlist_id,
    )
    if found and found[1]:
        return found

    info = fetch_deezer_playlist_info(playlist_id)
    return info["title"], _public_playlist_tracks(playlist_id)


def _public_playlist_tracks(playlist_id: str):
    """Every track from the public API. /playlist/{id} lists at most 400 of
    them, so the paginated /playlist/{id}/tracks is read instead."""
    tracks = list(public_pages(f"/playlist/{playlist_id}/tracks"))
    parsed = []

    for idx, t in enumerate(tracks, start=1):
        artist_name = ((t.get("artist") or {}).get("name")) or ""
        album_title = ((t.get("album") or {}).get("title")) or ""
        title = t.get("title", "") or ""
        duration = t.get("duration", None)
        parsed.append(
            {
                "position": idx,
                "track_id": t.get("id"),
                "title": title,
                "artist": artist_name,
                "album": album_title,
                "duration": duration,
                "norm_title": normalize_text(title),
                "norm_artist": normalize_text(artist_name),
                "norm_album": normalize_text(album_title),
                "version_flags": extract_version_flags(title, artist_name),
            }
        )

    return parsed


def follow_mix(kind: str, source_id: str, title: str, accounts=None, deezer_account=None):
    """Adds a mix of a Deezer account to the followed playlists; its cover is the
    album art of its first track."""
    from core.deezer_account import mix_tracks

    pid = mix_id(kind, source_id, deezer_account)
    if _saved_entry(pid):
        return pid, False
    tracks = mix_tracks(kind, source_id, account=deezer_account)
    entry = {"id": pid, "title": title, "picture": next((t["picture"] for t in tracks if t.get("picture")), "")}
    if accounts:
        entry["accounts"] = list(accounts)
    if not add_entry(entry):
        return pid, False
    cache_cover(entry)
    return pid, True


def map_host_path_to_navidrome(path: Path, mappings):
    path = path.resolve()
    for host_root, nav_root in mappings.items():
        try:
            rel = path.relative_to(host_root.resolve())
            return nav_root / rel
        except ValueError:
            continue
    raise ValueError(f"Unmapped path for Navidrome: {path}")


def relative_m3u_path(playlist_dir_host: Path, audio_file_host: Path, mappings) -> str:
    try:
        playlist_dir_nav = map_host_path_to_navidrome(playlist_dir_host, mappings)
    except ValueError:
        playlist_dir_nav = playlist_dir_host
    audio_file_nav = map_host_path_to_navidrome(audio_file_host, mappings)
    rel = os.path.relpath(str(audio_file_nav), start=str(playlist_dir_nav)).replace(
        os.sep, "/"
    )
    return rel if rel.startswith(".") else "./" + rel


def build_playlist_preview(playlist_id: str):
    if is_auto_id(playlist_id):
        return get_preview_state(playlist_id) or {
            "playlist_id": playlist_id, "playlist_title": playlist_title(playlist_id), "rows": [],
            "matched_count": 0, "unmatched_count": 0, "unchecked_count": 0,
        }
    title, deezer_tracks = fetch_deezer_playlist_tracks(playlist_id)
    saved_state = get_preview_state(playlist_id) or {}

    # Saved rows are found by Deezer track ID, so a reordered playlist keeps its results.
    saved_rows = saved_state.get("rows") if isinstance(saved_state.get("rows"), list) else []
    by_track = {str(r.get("track_id")): r for r in saved_rows if r.get("track_id")}
    by_number = {int(r["number"]): r for r in saved_rows if "number" in r}

    rows = []
    for track in deezer_tracks:
        old = by_track.get(str(track.get("track_id")))
        if old is None:
            legacy = by_number.get(track["position"])
            if legacy and not legacy.get("track_id"):
                old = legacy
        rows.append(_preview_row(track, old))

    preview = {
        "playlist_id": playlist_id,
        "playlist_title": title,
        "rows": rows,
        "matched_count": sum(1 for r in rows if r["matched"] is True),
        "unmatched_count": sum(1 for r in rows if r["matched"] is False),
        "unchecked_count": sum(1 for r in rows if r["matched"] is None),
    }
    if parse_xp_id(playlist_id):
        from core import crossplatform

        preview["xp"] = crossplatform.summary(playlist_id)
    return preview


def _preview_row(track, old=None):
    """Row of a track that this scan has not matched (yet): the result of the
    last scan when there is one, else "not checked"."""
    row = {
        "number": track["position"],
        "track_id": track.get("track_id"),
        "deezer_name": _deezer_name(track),
        "deezer_artist": track["artist"],
        "deezer_title": track["title"],
        "deezer_album": track["album"],
        "matched": None,
        "source_name": "",
        "manual": False,
        "downloaded": False,
    }
    if track.get("xp"):
        row["xp"] = track["xp"]
    if old:
        row.update({
            "matched": old.get("matched"),
            "source_name": old.get("source_name", "") if old.get("matched") else "",
            "local_path": old.get("local_path"),
            "manual": bool(old.get("manual")),
            "downloaded": bool(old.get("downloaded")),
        })
    return row


def _get_match_workers() -> int:
    try:
        cfg = load_config()
        val = cfg.get("match_workers")
        if val is not None:
            return max(1, int(val))
    except Exception:
        pass
    return max(1, int(os.environ.get("MATCH_WORKERS", "4") or "4"))


def _deezer_name(track):
    return f"{track['artist']} - {track['title']}" if track["artist"] else track["title"]


def _source_name(entry, audio_path: Path):
    title = (
        entry.get("tag_title")
        or entry.get("parsed_title")
        or entry.get("parsed_track_title")
        or audio_path.stem
    )
    artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
    return f"{artist} - {title}" if artist else title


def _row(track, entry=None, *, score=None, manual=False):
    """Preview row for one Deezer track; `entry` is the matched library entry or None."""
    row = {
        "number": track["position"],
        "track_id": track.get("track_id"),
        "deezer_name": _deezer_name(track),
        "deezer_artist": track["artist"],
        "deezer_title": track["title"],
        "deezer_album": track["album"],
        "manual": manual,
        "downloaded": False,
    }
    if track.get("xp"):
        row["xp"] = track["xp"]
    if entry is None:
        row.update({"convert": "❌", "matched": False, "source_name": "", "local_path": None})
    else:
        audio_path = Path(entry["path"])
        row.update({
            "convert": "✅",
            "matched": True,
            "source_name": _source_name(entry, audio_path),
            "local_path": str(audio_path),
        })
        if score is not None:
            row["score"] = score
    return row


def playlist_report(playlist_id: str, playlist_title: str, rows: list) -> dict:
    """What a scan found, without writing anything: for accounts that get their
    playlists through the Navidrome API rather than as files."""
    report = {"playlist_id": playlist_id, "playlist_title": playlist_title, "generated_at": int(time.time()),
              "matched_count": 0, "unmatched_count": 0, "tracks": []}
    for row in sorted(rows, key=lambda r: int(r["number"])):
        matched = row.get("matched") is True and bool(row.get("local_path"))
        report["matched_count" if matched else "unmatched_count"] += 1
        report["tracks"].append({"position": row["number"], "deezer_artist": row.get("deezer_artist", ""),
                                 "deezer_title": row.get("deezer_title", row.get("deezer_name", "")),
                                 "deezer_album": row.get("deezer_album", ""), "matched": matched})
    return report


def playlist_folder_name(playlist_id: str, title: str, remember=False) -> str:
    """The folder of a playlist's .m3u8, and the file's name in it. Kept once
    chosen (saved with the playlist): Navidrome knows a playlist by its file,
    so a title changed on Deezer must not make a second one. A name another
    playlist has already gets this one's ID: two "Chill" would share files."""
    entries = saved_entries()
    mine = next((e for e in entries if str(e.get("id")) == str(playlist_id)), None)
    if mine and mine.get("folder"):
        return str(mine["folder"])
    name = sanitize_filename(title) or f"playlist_{playlist_id}"
    taken = {str(e.get("folder") or "").casefold() for e in entries if str(e.get("id")) != str(playlist_id)}
    # Playlists saved before 1.19 have no folder yet: theirs is their title's.
    taken |= {(sanitize_filename(str(e.get("title") or "")) or f"playlist_{e.get('id')}").casefold()
              for e in entries if str(e.get("id")) != str(playlist_id) and not e.get("folder")
              and str(e.get("id")) < str(playlist_id)}
    if name.casefold() in taken:
        name = sanitize_filename(f"{name} [{playlist_id}]")
    if remember and mine is not None:
        def change(saved):
            for entry in saved:
                if str(entry.get("id")) == str(playlist_id) and not entry.get("folder"):
                    entry["folder"] = name
            return saved

        modify_playlists(change)
    return name


def write_playlist_outputs(playlist_id: str, playlist_title: str, rows: list):
    """Writes the .m3u8, report.json and missing.txt of a playlist from its preview rows."""
    _, playlists_base_dir, _, mappings = get_paths_from_config()
    folder = playlist_folder_name(playlist_id, playlist_title, remember=True)
    playlist_dir = playlists_base_dir / folder
    base = Path(os.path.realpath(playlists_base_dir))
    if base not in Path(os.path.realpath(playlist_dir)).parents:
        raise ValueError(f"Refused: {playlist_dir} is not in the playlists folder")
    playlist_dir.mkdir(parents=True, exist_ok=True)

    lines = ["#EXTM3U"]
    missing = []
    report = {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "generated_at": int(time.time()),
        "matched_count": 0,
        "unmatched_count": 0,
        "tracks": [],
    }
    for row in sorted(rows, key=lambda r: int(r["number"])):
        item = {
            "position": row["number"],
            "deezer_artist": row.get("deezer_artist", ""),
            "deezer_title": row.get("deezer_title", row.get("deezer_name", "")),
            "deezer_album": row.get("deezer_album", ""),
            "matched": row.get("matched") is True,
        }
        m3u_rel = None
        if row.get("matched") is True and row.get("local_path"):
            try:
                m3u_rel = relative_m3u_path(playlist_dir, Path(row["local_path"]), mappings)
            except ValueError:
                # A file outside every path mapping: that track is missing for
                # Navidrome, the others are still written.
                item["unmapped"] = True
        if m3u_rel is not None:
            lines.append(m3u_rel)
            report["matched_count"] += 1
            item.update({"local_path": row["local_path"], "m3u_relative_path": m3u_rel, "manual": bool(row.get("manual"))})
        else:
            report["unmatched_count"] += 1
            album = f" [{row['deezer_album']}]" if row.get("deezer_album") else ""
            missing.append(f"{row.get('deezer_name', '')}{album}")
        report["tracks"].append(item)

    m3u8_path = playlist_dir / f"{folder}.m3u8"
    # Navidrome may read the .m3u8 at any moment: never half-written.
    files.write_atomic(m3u8_path, "\n".join(lines) + "\n")
    files.write_json(playlist_dir / "report.json", report)
    files.write_atomic(playlist_dir / "missing.txt", "\n".join(missing) + ("\n" if missing else ""))
    return m3u8_path, report


def apply_manual_match(playlist_id: str, track_id: str, mode: str, path: str | None = None):
    """Pins one track of a playlist: to a library file ("file"), as missing
    ("missing"), or back to automatic matching ("auto"). Rewrites the playlist
    files and returns the updated row."""
    from core.library import library_snapshot

    entry = None
    if mode == "file":
        entry = library_snapshot()["by_path"].get(path or "")
        if entry is None:
            raise ValueError("This file is not in the library index")
    elif mode not in ("missing", "auto"):
        raise ValueError("Unknown mode")

    updated = {}

    def change(state):
        state = dict(state or {})
        rows = [dict(r) for r in state.get("rows") or []]
        row = next((r for r in rows if str(r.get("track_id")) == str(track_id)), None)
        if row is None:
            raise LookupError("Scan this playlist before fixing its matches")
        overrides = dict(state.get("overrides") or {})

        if mode == "auto":
            overrides.pop(str(track_id), None)
            row.update({"matched": None, "manual": False, "source_name": "", "local_path": None, "convert": "⚪"})
        elif mode == "missing":
            overrides[str(track_id)] = {"path": None}
            row.update({"matched": False, "manual": True, "source_name": "", "local_path": None, "convert": "❌"})
        else:
            overrides[str(track_id)] = {"path": entry["path"]}
            row.update({
                "matched": True,
                "manual": True,
                "source_name": _source_name(entry, Path(entry["path"])),
                "local_path": entry["path"],
                "convert": "✅",
                "downloaded": False,
            })
        row.pop("score", None)
        updated.update(row)
        state.update({"rows": rows, "overrides": overrides, "updated_at": int(time.time())})
        return state

    state = modify_preview_state(playlist_id, change)
    from core import publish

    publish.publish(playlist_id, state.get("playlist_title") or f"playlist_{playlist_id}", state["rows"])
    return updated


def rematch_track(playlist_id: str, track: dict):
    """Matches one track against the library again, after its Deezer track
    changed, and saves its row. A file chosen by hand ("Fix") still wins.
    Returns the row; a playlist never scanned only gets the preview row."""
    from core.library import library_snapshot

    if not (get_preview_state(playlist_id) or {}).get("rows"):
        return _preview_row(track)

    snap = library_snapshot()
    updated = {}

    def change(state):
        state = dict(state or {})
        override = (state.get("overrides") or {}).get(str(track["track_id"]))
        if override is not None and override.get("path") is None:
            row = _row(track, None, manual=True)
        elif override is not None and override.get("path") in snap["by_path"]:
            row = _row(track, snap["by_path"][override["path"]], manual=True)
        else:
            best = find_best_match(track, snap["library"], snap["index"])
            row = _row(track, best["entry"], score=best["score"]) if best else _row(track, None)
        rows = [r for r in state.get("rows") or [] if int(r.get("number", 0)) != track["position"]]
        rows.append(row)
        rows.sort(key=lambda r: int(r["number"]))
        updated.update(row)
        state.update({"rows": rows, "updated_at": int(time.time())})
        return state

    state = modify_preview_state(playlist_id, change)
    from core import publish

    publish.publish(playlist_id, state.get("playlist_title") or playlist_title(playlist_id), state["rows"])
    return updated


def convert_playlist(playlist_id: str, progress_cb=None, quick: bool = False):
    def emit(message=None, progress=None, stage=None, row_update=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage, row_update=row_update)

    _, _, library_cache_file, _ = get_paths_from_config()

    saved = get_preview_state(playlist_id) or {}
    saved_by_track = {str(r.get("track_id")): r for r in saved.get("rows", []) if r.get("track_id")}

    def on_source_match(done, total, track):
        # Imported playlists: each track appears as soon as its Deezer pick is known.
        emit(
            f"Finding on Deezer {done}/{total}: {track['xp']['source_artist']} - {track['xp']['source_title']}",
            stage="deezer",
            progress=round(done / total * 100),
            row_update=_preview_row(track, saved_by_track.get(str(track["track_id"]))),
        )

    if parse_xp_id(playlist_id):
        emit("Reading the source playlist", stage="deezer")
    else:
        emit("Fetching Deezer playlist info", stage="deezer")
    playlist_title, deezer_tracks = fetch_deezer_playlist_tracks(
        playlist_id, refresh=True, full=not quick, progress=on_source_match
    )

    library = load_library_cache(library_cache_file)
    if not library:
        emit("Library cache empty, running full rebuild", stage="cache")
        rebuild_library_cache_full_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: emit(
                message=message, progress=progress, stage=stage
            )
        )
        library = load_library_cache(library_cache_file)
    by_path = {e["path"]: e for e in library}

    # Read again: matching an imported playlist may have moved manual choices.
    saved = get_preview_state(playlist_id) or {}
    saved_by_track = {str(r.get("track_id")): r for r in saved.get("rows", []) if r.get("track_id")}
    overrides = saved.get("overrides") or {}

    rows: dict[int, dict] = {}

    def keep(track, row):
        # A downloaded track stays marked until it shows up in the library.
        old = saved_by_track.get(str(track.get("track_id"))) or {}
        row["downloaded"] = bool(old.get("downloaded")) and not row["matched"]
        rows[track["position"]] = row
        emit(row_update=row)

    # Manual choices win over matching, in quick and full scans alike.
    to_match = []
    for track in deezer_tracks:
        override = overrides.get(str(track.get("track_id")))
        if override is not None:
            path = override.get("path")
            if path is None:
                keep(track, _row(track, None, manual=True))
                continue
            # Trust the library index: a manual choice survives a briefly unmounted disk.
            if path in by_path:
                keep(track, _row(track, by_path[path], manual=True))
                continue
        to_match.append(track)

    # Quick mode: reuse earlier automatic matches whose file still exists.
    if quick:
        remaining = []
        for track in to_match:
            old = saved_by_track.get(str(track.get("track_id")))
            path = (old or {}).get("local_path")
            if old and old.get("matched") is True and path in by_path and Path(path).exists():
                keep(track, _row(track, by_path[path], score=old.get("score")))
            else:
                remaining.append(track)
        to_match = remaining

    total = len(to_match)
    reused = len(deezer_tracks) - total
    emit(
        f"Matching {total} tracks" + (f", {reused} already settled" if reused else ""),
        stage="matching",
        progress=0,
    )

    if total:
        index = build_title_index(library)
        workers = _get_match_workers() if total > 1 else 1
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(find_best_match, t, library, index): t for t in to_match}
            for done, future in enumerate(as_completed(futures), start=1):
                track = futures[future]
                best = future.result()
                keep(track, _row(track, best["entry"], score=best["score"]) if best else _row(track, None))
                emit(
                    f"Matching {done}/{total}: {_deezer_name(track)}",
                    stage="matching",
                    progress=round(done / total * 100),
                )

    emit("Writing output files", stage="write", progress=100)
    ordered = [rows[t["position"]] for t in deezer_tracks]
    from core import publish

    m3u8_path, report = publish.publish(playlist_id, playlist_title, ordered)

    def merge(state):
        # Overrides may have changed while the scan ran: keep the latest ones.
        return {
            "playlist_id": playlist_id,
            "playlist_title": playlist_title,
            "updated_at": int(time.time()),
            "rows": ordered,
            "overrides": (state or {}).get("overrides") or {},
        }

    modify_preview_state(playlist_id, merge)

    return {
        "playlist_title": playlist_title,
        "matched": report["matched_count"],
        "unmatched": report["unmatched_count"],
        "path": str(m3u8_path) if m3u8_path else "",
    }


def mark_preview_rows_downloaded(playlist_id, downloaded_ids):
    """Marks the tracks as downloaded.

    The read and the write are done in one locked step: several downloads can
    finish at the same time, and they must not overwrite each other."""
    if not downloaded_ids:
        return []

    changed_rows = []

    def change(state):
        if not state or not isinstance(state.get("rows"), list):
            return state
        for row in state["rows"]:
            tid = str(row.get("track_id") or "").strip()
            if not tid or tid not in downloaded_ids:
                continue
            if row.get("downloaded") is True:
                continue
            row["downloaded"] = True
            changed_rows.append(dict(row))
        if changed_rows:
            state["updated_at"] = int(time.time())
        return state

    modify_preview_state(playlist_id, change)
    return changed_rows


def search_deezer(query: str, search_type: str, limit: int = 25):
    query = (query or "").strip()
    if not query:
        return []

    type_map = {"track": "track", "album": "album", "artist": "artist"}
    endpoint = type_map.get(search_type, "track")

    resp = requests.get(
        f"https://api.deezer.com/search/{endpoint}",
        params={"q": query, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))

    results = []
    for item in payload.get("data", []):
        if search_type == "track":
            artist_name = ((item.get('artist') or {}).get('name')) or ''
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "type": "track",
                    "title": item.get("title") or "Unknown title",
                    "artist": artist_name,
                    "subtitle": f"{artist_name or 'Artiste inconnu'} • {((item.get('album') or {}).get('title')) or 'Album inconnu'}",
                    "album": ((item.get("album") or {}).get("title")) or "",
                    "duration": item.get("duration"),
                    "explicit": bool(item.get("explicit_lyrics")),
                    "cover": ((item.get("album") or {}).get("cover_medium"))
                    or ((item.get("album") or {}).get("cover_small"))
                    or "",
                    "download_type": "track",
                    "download_id": str(item.get("id") or ""),
                }
            )
        elif search_type == "album":
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "type": "album",
                    "title": item.get("title") or "Album inconnu",
                    "subtitle": ((item.get("artist") or {}).get("name")) or "Artiste inconnu",
                    "artist": ((item.get("artist") or {}).get("name")) or "",
                    "cover": item.get("cover_medium") or item.get("cover_small") or "",
                    "track_count": item.get("nb_tracks", 0),
                    "explicit": bool(item.get("explicit_lyrics")),
                    "download_type": "album",
                    "download_id": str(item.get("id") or ""),
                }
            )
        elif search_type == "artist":
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "type": "artist",
                    "title": item.get("name") or "Artiste inconnu",
                    "subtitle": f"{item.get('nb_album', 0)} albums",
                    "nb_album": item.get("nb_album", 0),
                    "cover": item.get("picture_medium") or item.get("picture_small") or "",
                    "download_type": "artist",
                    "download_id": str(item.get("id") or ""),
                }
            )
    return results


# Deezer's public API allows about 50 requests per 5 seconds: the album track
# lists fetched for the ownership chips are spaced out, and kept for a while
# since a released album does not change.
_API_GAP = 0.12
_api_gate = threading.Lock()
_api_last = [0.0]
_ALBUM_TRACKS_TTL = 6 * 3600
_album_tracks = {}


def _public_api(path, params=None):
    for attempt in range(3):
        with _api_gate:
            wait = _api_last[0] + _API_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            _api_last[0] = time.time()
        # English names: genres end up in file tags, and Deezer otherwise follows the
        # server's country ("Films/Jeux vidéo").
        data = requests.get(f"https://api.deezer.com{path}", params=params, timeout=30,
                            headers={"Accept-Language": "en"}).json()
        error = data.get("error") if isinstance(data, dict) else None
        if error and error.get("code") == 4 and attempt < 2:
            time.sleep(1.5)  # quota exceeded: wait for the window to pass
            continue
        if error:
            raise RuntimeError(str(error))
        return data


def public_pages(path, params=None, page_size=100):
    """Every item of a paginated list of the public API, page after page,
    through _public_api: its pace, and its wait when Deezer's quota is reached.
    An error answer is raised, never taken for an empty list."""
    index = 0
    while True:
        page = _public_api(path, {**(params or {}), "limit": page_size, "index": index})
        data = page.get("data") or []
        yield from data
        index += len(data)
        if not data or index >= int(page.get("total") or 0):
            return


def fetch_deezer_album_tracks(album_id: str):
    """Every track of an album. /album/{id} lists at most 25 of them, so the
    paginated /album/{id}/tracks is used instead."""
    album_id = str(album_id)
    cached = _album_tracks.get(album_id)
    if cached and time.time() - cached[0] < _ALBUM_TRACKS_TTL:
        return cached[1]
    tracks = list(public_pages(f"/album/{album_id}/tracks"))
    if len(_album_tracks) > 2000:
        _album_tracks.clear()
    _album_tracks[album_id] = (time.time(), tracks)
    return tracks


def fetch_deezer_album_details(album_id: str):
    resp = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))

    tracks = []
    for idx, t in enumerate(fetch_deezer_album_tracks(album_id), start=1):
        tracks.append(
            {
                "position": idx,
                "track_id": str(t.get("id") or ""),
                "title": t.get("title") or "Unknown title",
                "artist": ((t.get("artist") or {}).get("name"))
                or ((data.get("artist") or {}).get("name"))
                or "",
                "duration": t.get("duration"),
                "explicit": bool(t.get("explicit_lyrics")),
            }
        )

    return {
        "id": str(data.get("id") or album_id),
        "type": "album",
        "title": data.get("title") or "Album inconnu",
        "artist": ((data.get("artist") or {}).get("name")) or "Artiste inconnu",
        "cover": data.get("cover_big")
        or data.get("cover_medium")
        or data.get("cover_small")
        or "",
        "track_count": data.get("nb_tracks") or len(tracks),
        "explicit": bool(data.get("explicit_lyrics")),
        "tracks": tracks,
    }


def fetch_deezer_artist_albums(artist_id: str):
    """Every release of the artist: one page held only 50, so an artist with
    more lost the rest."""
    albums = []
    for item in public_pages(f"/artist/{int(artist_id)}/albums"):
        albums.append(
            {
                "id": str(item.get("id") or ""),
                "title": item.get("title") or "Album inconnu",
                "cover": item.get("cover_medium") or item.get("cover_small") or "",
                "release_date": item.get("release_date") or "",
                "record_type": item.get("record_type") or "",
                "explicit": bool(item.get("explicit_lyrics")),
            }
        )
    return albums


def fetch_deezer_artist_details(artist_id: str):
    resp = requests.get(f"https://api.deezer.com/artist/{artist_id}", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return {
        "id": str(data.get("id") or artist_id),
        "type": "artist",
        "name": data.get("name") or "Artiste inconnu",
        "picture": data.get("picture_big")
        or data.get("picture_medium")
        or data.get("picture_small")
        or "",
        "nb_album": data.get("nb_album", 0),
        "albums": fetch_deezer_artist_albums(artist_id),
    }


def submit_missing_downloads(playlist_id: str) -> int:
    """Queue the download of every unmatched track of a playlist.

    Does not wait for completion. Returns the number of tracks queued.
    Used by the auto-scan scheduler.
    """
    from core.download_queue import enqueue_download

    preview = get_preview_state(str(playlist_id))
    if not preview or not isinstance(preview.get("rows"), list):
        return 0

    missing_rows = [
        row for row in preview["rows"]
        if row.get("matched") is False
        and row.get("track_id")
        and not row.get("downloaded")
    ]

    def done(task, result, error):
        # Marked, so the next scan does not ask for it again.
        if not error:
            mark_preview_rows_downloaded(str(playlist_id), {str(task.music_id)})

    submitted = 0
    for row in missing_rows:
        track_id = str(row["track_id"]).strip()
        if not track_id.isdigit():
            continue
        try:
            enqueue_download("track", track_id, on_done=done)
            submitted += 1
        except Exception:
            pass
    return submitted
