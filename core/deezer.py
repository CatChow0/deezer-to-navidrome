import ast
import html
import json
import os
import re
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
    update_preview_state,
)
from core.library import load_library_cache, rebuild_library_cache_full_with_progress
from core.normalization import extract_version_flags, normalize_text
from core.matching import build_title_index, find_best_match
from core.utils import sanitize_filename


def fetch_deezer_playlist_info(playlist_id: str):
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


def save_playlists(playlists):
    ensure_dirs()
    cleaned = []
    seen = set()
    for item in playlists:
        pid = str(item.get("id", "")).strip()
        if not pid.isdigit() or pid in seen:
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
        cleaned.append(entry)
        seen.add(pid)

    cleaned.sort(key=lambda x: int(x["id"]))
    PLAYLIST_IDS_FILE.write_text(
        json.dumps({"playlists": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_playlists():
    ensure_dirs()
    if not PLAYLIST_IDS_FILE.exists():
        return []

    try:
        data = json.loads(PLAYLIST_IDS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    playlists = []
    changed = False

    if isinstance(data.get("playlists"), list):
        for item in data["playlists"]:
            pid = str(item.get("id", "")).strip()
            if not pid.isdigit():
                continue
            title = str(item.get("title", "")).strip()
            picture = str(item.get("picture", "")).strip()
            if not title or not picture:
                try:
                    info = fetch_deezer_playlist_info(pid)
                    title = title or info["title"]
                    picture = picture or info["picture"]
                    changed = True
                except Exception:
                    title = title or "Unknown title"
            playlists.append({
                "id": pid,
                "title": title,
                "picture": picture,
                "auto_scan_enabled": bool(item.get("auto_scan_enabled", False)),
                "auto_scan_interval_minutes": max(1, int(item.get("auto_scan_interval_minutes") or 60)),
                "auto_download_after_scan": bool(item.get("auto_download_after_scan", False)),
            })
    elif isinstance(data.get("playlist_ids"), list):
        for raw in data["playlist_ids"]:
            pid = str(raw).strip()
            if not pid.isdigit():
                continue
            try:
                info = fetch_deezer_playlist_info(pid)
                playlists.append(info)
            except Exception:
                playlists.append({"id": pid, "title": "Unknown title", "picture": ""})
                changed = True

    playlists = sorted(
        {p["id"]: p for p in playlists}.values(), key=lambda x: int(x["id"])
    )

    if changed:
        save_playlists(playlists)

    for p in playlists:
        p["cover_cached"] = cache_cover(p)

    return playlists


def playlist_title(playlist_id: str) -> str:
    """Title from the saved playlists file, without calling Deezer."""
    try:
        data = json.loads(PLAYLIST_IDS_FILE.read_text(encoding="utf-8"))
        for item in data.get("playlists") or []:
            if str(item.get("id")) == str(playlist_id):
                return item.get("title") or str(playlist_id)
    except Exception:
        pass
    return str(playlist_id)


def fetch_deezer_playlist_tracks(playlist_id: str):
    info = fetch_deezer_playlist_info(playlist_id)
    url = f"https://api.deezer.com/playlist/{playlist_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    payload = r.json()

    tracks = payload.get("tracks", {}).get("data", [])
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

    return info["title"], parsed


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
    playlist_title, deezer_tracks = fetch_deezer_playlist_tracks(playlist_id)
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
        if old:
            row.update({
                "matched": old.get("matched"),
                "source_name": old.get("source_name", "") if old.get("matched") else "",
                "local_path": old.get("local_path"),
                "manual": bool(old.get("manual")),
                "downloaded": bool(old.get("downloaded")),
            })
        rows.append(row)

    return {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "rows": rows,
        "matched_count": sum(1 for r in rows if r["matched"] is True),
        "unmatched_count": sum(1 for r in rows if r["matched"] is False),
        "unchecked_count": sum(1 for r in rows if r["matched"] is None),
    }


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


def write_playlist_outputs(playlist_id: str, playlist_title: str, rows: list):
    """Writes the .m3u8, report.json and missing.txt of a playlist from its preview rows."""
    _, playlists_base_dir, _, mappings = get_paths_from_config()
    folder = sanitize_filename(playlist_title) or f"playlist_{playlist_id}"
    playlist_dir = playlists_base_dir / folder
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
        if row.get("matched") is True and row.get("local_path"):
            m3u_rel = relative_m3u_path(playlist_dir, Path(row["local_path"]), mappings)
            lines.append(m3u_rel)
            report["matched_count"] += 1
            item.update({"local_path": row["local_path"], "m3u_relative_path": m3u_rel, "manual": bool(row.get("manual"))})
        else:
            report["unmatched_count"] += 1
            album = f" [{row['deezer_album']}]" if row.get("deezer_album") else ""
            missing.append(f"{row.get('deezer_name', '')}{album}")
        report["tracks"].append(item)

    m3u8_path = playlist_dir / f"{folder}.m3u8"
    m3u8_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (playlist_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (playlist_dir / "missing.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
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
    write_playlist_outputs(playlist_id, state.get("playlist_title") or f"playlist_{playlist_id}", state["rows"])
    return updated


def convert_playlist(playlist_id: str, progress_cb=None, quick: bool = False):
    def emit(message=None, progress=None, stage=None, row_update=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage, row_update=row_update)

    _, _, library_cache_file, _ = get_paths_from_config()

    emit("Fetching Deezer playlist info", stage="deezer")
    playlist_title, deezer_tracks = fetch_deezer_playlist_tracks(playlist_id)

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

    saved = get_preview_state(playlist_id) or {}
    saved_by_track = {str(r.get("track_id")): r for r in saved.get("rows", []) if r.get("track_id")}
    overrides = saved.get("overrides") or {}

    rows: dict[int, dict] = {}

    def keep(track, row):
        # A track sent to Deezer Downloader stays marked until it shows up in the library.
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
    m3u8_path, report = write_playlist_outputs(playlist_id, playlist_title, ordered)

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
        "path": str(m3u8_path),
    }


def parse_queue_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("queue", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def extract_track_id_from_queue_item(item):
    args = item.get("args")

    if isinstance(args, dict):
        for key in ("track_id", "music_id", "id", "trackId", "musicId"):
            value = args.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    if isinstance(args, str):
        raw = html.unescape(args)
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                for key in ("track_id", "music_id", "id", "trackId", "musicId"):
                    value = parsed.get(key)
                    if value is not None and str(value).strip():
                        return str(value).strip()
        except Exception:
            pass

        m = re.search(r"track_id['\"]?\s*[:=]\s*(\d+)", raw, re.IGNORECASE)
        if m:
            return m.group(1)

    for key in ("track_id", "music_id", "trackId", "musicId"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def extract_queue_state(item):
    for key in ("state", "status"):
        value = item.get(key)
        if value is not None:
            return str(value).strip().lower()
    return ""


def mark_preview_rows_downloaded(playlist_id, downloaded_ids):
    if not downloaded_ids:
        return []

    state = get_preview_state(playlist_id)
    if not state or not isinstance(state.get("rows"), list):
        return []

    changed_rows = []
    changed = False

    for row in state["rows"]:
        tid = str(row.get("track_id") or "").strip()
        if not tid or tid not in downloaded_ids:
            continue
        if row.get("downloaded") is True:
            continue
        row["downloaded"] = True
        changed = True
        changed_rows.append(dict(row))

    if changed:
        state["updated_at"] = int(time.time())
        update_preview_state(playlist_id, state)

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


def fetch_deezer_album_details(album_id: str):
    resp = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))

    tracks = []
    for idx, t in enumerate((data.get("tracks") or {}).get("data", []), start=1):
        tracks.append(
            {
                "position": idx,
                "track_id": str(t.get("id") or ""),
                "title": t.get("title") or "Unknown title",
                "artist": ((t.get("artist") or {}).get("name"))
                or ((data.get("artist") or {}).get("name"))
                or "",
                "duration": t.get("duration"),
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
        "tracks": tracks,
    }


def fetch_deezer_artist_albums(artist_id: str, limit: int = 50):
    resp = requests.get(
        f"https://api.deezer.com/artist/{artist_id}/albums",
        params={"limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))

    albums = []
    for item in data.get("data", []):
        albums.append(
            {
                "id": str(item.get("id") or ""),
                "title": item.get("title") or "Album inconnu",
                "cover": item.get("cover_medium") or item.get("cover_small") or "",
                "release_date": item.get("release_date") or "",
                "record_type": item.get("record_type") or "",
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


def submit_missing_downloads(playlist_id: str, base_url: str) -> int:
    """Fire download requests for all unmatched tracks in a playlist.

    Does not wait for completion. Returns the number of requests sent.
    Used by the auto-scan scheduler.
    """
    preview = get_preview_state(str(playlist_id))
    if not preview or not isinstance(preview.get("rows"), list):
        return 0

    missing_rows = [
        row for row in preview["rows"]
        if row.get("matched") is False
        and row.get("track_id")
        and not row.get("downloaded")
    ]

    submitted = 0
    for row in missing_rows:
        track_id = str(row["track_id"]).strip()
        try:
            requests.post(
                f"{base_url}/download",
                json={
                    "type": "track",
                    "music_id": int(track_id),
                    "add_to_playlist": False,
                    "create_zip": False,
                },
                timeout=10,
            )
            submitted += 1
        except Exception:
            pass
    return submitted
