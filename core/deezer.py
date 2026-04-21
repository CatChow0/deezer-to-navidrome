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
    update_preview_state,
)
from core.library import load_library_cache, rebuild_library_cache_full_with_progress
from core.normalization import extract_version_flags, normalize_text
from core.utils import sanitize_filename, similarity


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


def score_candidate(track, entry):
    title_candidates = [
        entry.get("norm_tag_title"),
        entry.get("norm_parsed_title"),
        entry.get("norm_parsed_track_title"),
        entry.get("stem_norm"),
    ]
    artist_candidates = [
        entry.get("norm_tag_artist"),
        entry.get("norm_parsed_artist"),
        entry.get("artist_dir_norm"),
    ]
    album_candidates = [
        entry.get("norm_tag_album"),
        entry.get("album_dir_norm"),
    ]

    title_score = max(
        (similarity(track["norm_title"], x) for x in title_candidates if x),
        default=0.0,
    )
    artist_score = max(
        (similarity(track["norm_artist"], x) for x in artist_candidates if x),
        default=0.0,
    )
    album_score = max(
        (similarity(track["norm_album"], x) for x in album_candidates if x),
        default=0.0,
    )

    score = 0.0
    score += title_score * 0.62
    score += artist_score * 0.25
    score += album_score * 0.08

    td = track.get("duration")
    ld = entry.get("duration")
    if td and ld:
        diff = abs(float(td) - float(ld))
        if diff <= 2:
            score += 0.10
        elif diff <= 5:
            score += 0.07
        elif diff <= 10:
            score += 0.04
        elif diff > 20:
            score -= 0.08

    # Version flag comparison — disambiguates remix/live/radio edit variants
    track_flags = set(track.get("version_flags") or [])
    entry_flags = set(entry.get("version_flags") or [])
    if track_flags or entry_flags:
        if track_flags == entry_flags:
            score += 0.08  # exact match (e.g. both remix)
        else:
            diff_flags = track_flags.symmetric_difference(entry_flags)
            # Ignore "remaster" conflicts — remastered and original are interchangeable
            meaningful = diff_flags - {"remaster"}
            if meaningful:
                score -= 0.18  # real version mismatch (remix vs original, live vs studio)
            else:
                score -= 0.03  # only remaster differs, minor penalty

    return {
        "score": round(score, 4),
        "title_score": round(title_score, 4),
        "artist_score": round(artist_score, 4),
        "album_score": round(album_score, 4),
    }


def build_title_index(library: list) -> dict[str, list[int]]:
    """Inverted word index: {word -> [entry_indices]} for fast candidate pre-filtering."""
    idx: dict[str, list[int]] = {}
    for i, entry in enumerate(library):
        seen: set[str] = set()
        for field in ("norm_tag_title", "norm_parsed_title", "norm_parsed_track_title", "stem_norm"):
            for word in (entry.get(field) or "").split():
                if len(word) >= 4 and word not in seen:
                    seen.add(word)
                    idx.setdefault(word, []).append(i)
    return idx


def find_best_match(track, library, title_index=None):
    candidates = library
    if title_index is not None:
        query_words = [w for w in track["norm_title"].split() if len(w) >= 4]
        if query_words:
            lib_size = len(library)
            candidate_indices: set[int] = set()
            for word in query_words:
                hits = title_index.get(word, [])
                # Skip words present in >20% of the library — too common to be discriminating
                if len(hits) < lib_size * 0.20:
                    candidate_indices.update(hits)
            if candidate_indices:
                candidates = [library[i] for i in candidate_indices]

    best = None
    best_data = None
    for entry in candidates:
        scored = score_candidate(track, entry)
        if scored["title_score"] < 0.72:
            continue
        if track["norm_artist"] and scored["artist_score"] < 0.45:
            continue
        if best is None or scored["score"] > best:
            best = scored["score"]
            best_data = {"entry": entry, **scored}
    return best_data


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
    saved_state = get_preview_state(playlist_id)

    rows = []
    saved_rows = {}
    if saved_state and isinstance(saved_state.get("rows"), list):
        saved_rows = {int(r["number"]): r for r in saved_state["rows"] if "number" in r}

    for track in deezer_tracks:
        deezer_name = (
            f"{track['artist']} - {track['title']}" if track["artist"] else track["title"]
        )
        old = saved_rows.get(track["position"])
        if old:
            rows.append(
                {
                    "convert": old.get("convert", "⚪"),
                    "number": track["position"],
                    "deezer_name": deezer_name,
                    "source_name": old.get("source_name", ""),
                    "matched": old.get("matched"),
                    "track_id": old.get("track_id") or track.get("track_id"),
                    "downloaded": bool(old.get("downloaded")),
                }
            )
        else:
            rows.append(
                {
                    "convert": "⚪",
                    "number": track["position"],
                    "deezer_name": deezer_name,
                    "source_name": "",
                    "matched": None,
                    "track_id": track.get("track_id"),
                    "downloaded": False,
                }
            )

    matched_count = sum(1 for r in rows if r["matched"] is True)
    unmatched_count = sum(1 for r in rows if r["matched"] is False)
    unchecked_count = sum(1 for r in rows if r["matched"] is None)

    return {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "rows": rows,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "unchecked_count": unchecked_count,
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


def convert_playlist(playlist_id: str, progress_cb=None, quick: bool = False):
    def emit(message=None, progress=None, stage=None, row_update=None):
        if progress_cb:
            progress_cb(
                message=message,
                progress=progress,
                stage=stage,
                row_update=row_update,
            )

    _, playlists_base_dir, library_cache_file, mappings = get_paths_from_config()

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

    emit("Building title index", stage="matching", progress=0)
    title_index = build_title_index(library)
    match_workers = _get_match_workers()

    # Quick mode: reuse already-matched rows from previous scan
    cached_rows: dict[int, dict] = {}
    if quick:
        saved = get_preview_state(playlist_id)
        if saved and isinstance(saved.get("rows"), list):
            # Build a source_name index for backward compat (old cache rows have no local_path)
            _source_index: dict[str, str] = {}
            for entry in library:
                ea = entry.get("tag_artist") or entry.get("parsed_artist") or ""
                et = (
                    entry.get("tag_title")
                    or entry.get("parsed_title")
                    or entry.get("parsed_track_title")
                    or Path(entry["path"]).stem
                )
                sn = f"{ea} - {et}" if ea else et
                norm_sn = normalize_text(sn)
                if norm_sn:
                    _source_index[norm_sn] = entry["path"]

            for r in saved["rows"]:
                if r.get("matched") is not True:
                    continue
                local_path = r.get("local_path")
                if local_path:
                    p = Path(local_path)
                    if p.exists():
                        cached_rows[r["number"]] = r
                else:
                    # Old cache format: no local_path, use source_name to find it
                    norm_sn = normalize_text(r.get("source_name", ""))
                    if norm_sn and norm_sn in _source_index:
                        p = Path(_source_index[norm_sn])
                        if p.exists():
                            cached_rows[r["number"]] = {**r, "local_path": str(p)}

    tracks_to_match = [t for t in deezer_tracks if t["position"] not in cached_rows]
    skipped = len(cached_rows)
    total_to_match = len(tracks_to_match)

    if quick and skipped:
        emit(
            f"Quick scan: {skipped} cached, matching {total_to_match} tracks",
            stage="matching",
            progress=0,
        )
    else:
        emit("Matching tracks", stage="matching", progress=0)

    match_results: dict[int, object] = {}
    if total_to_match > 0:
        if match_workers > 1 and total_to_match > 1:
            done_count = 0
            with ThreadPoolExecutor(max_workers=match_workers) as executor:
                future_to_track = {
                    executor.submit(find_best_match, t, library, title_index): t
                    for t in tracks_to_match
                }
                for future in as_completed(future_to_track):
                    done_count += 1
                    t = future_to_track[future]
                    match_results[t["position"]] = future.result()
                    emit(
                        f"Matching {done_count}/{total_to_match}: {t['artist']} - {t['title']}",
                        stage="matching",
                        progress=round(done_count / total_to_match * 100),
                    )
        else:
            for idx, t in enumerate(tracks_to_match, start=1):
                emit(
                    f"Matching {idx}/{total_to_match}: {t['artist']} - {t['title']}",
                    stage="matching",
                    progress=round(idx / total_to_match * 100),
                )
                match_results[t["position"]] = find_best_match(t, library, title_index)

    # Build output in playlist order
    playlist_folder_name = sanitize_filename(playlist_title) or f"playlist_{playlist_id}"
    playlist_dir = playlists_base_dir / playlist_folder_name
    playlist_dir.mkdir(parents=True, exist_ok=True)

    m3u8_path = playlist_dir / f"{playlist_folder_name}.m3u8"
    report_path = playlist_dir / "report.json"
    missing_path = playlist_dir / "missing.txt"

    lines = ["#EXTM3U"]
    report = {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "generated_at": int(time.time()),
        "matched_count": 0,
        "unmatched_count": 0,
        "tracks": [],
    }
    missing_lines = []
    preview_rows = []

    for track in deezer_tracks:
        pos = track["position"]
        deezer_name = (
            f"{track['artist']} - {track['title']}" if track["artist"] else track["title"]
        )

        item = {
            "position": pos,
            "deezer_artist": track["artist"],
            "deezer_title": track["title"],
            "deezer_album": track["album"],
        }

        # Use cached result if available (quick mode)
        if pos in cached_rows and pos not in match_results:
            cached = cached_rows[pos]
            audio_path = Path(cached["local_path"])
            m3u_rel = relative_m3u_path(playlist_dir, audio_path, mappings)
            lines.append(m3u_rel)
            report["matched_count"] += 1
            item.update({"matched": True, "local_path": str(audio_path), "m3u_relative_path": m3u_rel})
            preview_row = {**cached, "deezer_name": deezer_name}
            report["tracks"].append(item)
            preview_rows.append(preview_row)
            emit(row_update=preview_row)
            continue

        best = match_results.get(pos)

        if best is None:
            report["unmatched_count"] += 1
            item["matched"] = False
            missing_lines.append(f"{track['artist']} - {track['title']} [{track['album']}]")
            preview_row = {
                "convert": "❌",
                "number": pos,
                "deezer_name": deezer_name,
                "source_name": "not found",
                "matched": False,
                "local_path": None,
                "track_id": track.get("track_id"),
                "downloaded": False,
            }
        else:
            audio_path = Path(best["entry"]["path"])
            m3u_rel = relative_m3u_path(playlist_dir, audio_path, mappings)
            lines.append(m3u_rel)
            report["matched_count"] += 1
            item.update(
                {
                    "matched": True,
                    "local_path": str(audio_path),
                    "m3u_relative_path": m3u_rel,
                    "score": best["score"],
                }
            )
            entry = best["entry"]
            source_title = (
                entry.get("tag_title")
                or entry.get("parsed_title")
                or entry.get("parsed_track_title")
                or audio_path.stem
            )
            source_artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
            source_name = f"{source_artist} - {source_title}" if source_artist else source_title
            preview_row = {
                "convert": "✅",
                "number": pos,
                "deezer_name": deezer_name,
                "source_name": source_name,
                "matched": True,
                "local_path": str(audio_path),
                "track_id": track.get("track_id"),
                "downloaded": False,
            }

        report["tracks"].append(item)
        preview_rows.append(preview_row)
        emit(row_update=preview_row)

    emit("Writing output files", stage="write", progress=100)

    m3u8_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    missing_path.write_text(
        "\n".join(missing_lines) + ("\n" if missing_lines else ""), encoding="utf-8"
    )

    update_preview_state(
        playlist_id,
        {
            "playlist_id": playlist_id,
            "playlist_title": playlist_title,
            "updated_at": int(time.time()),
            "rows": preview_rows,
        },
    )

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
            results.append(
                {
                    "id": str(item.get("id") or ""),
                    "type": "track",
                    "title": item.get("title") or "Unknown title",
                    "subtitle": f"{((item.get('artist') or {}).get('name')) or 'Artiste inconnu'} • {((item.get('album') or {}).get('title')) or 'Album inconnu'}",
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
                    "cover": item.get("cover_medium") or item.get("cover_small") or "",
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
