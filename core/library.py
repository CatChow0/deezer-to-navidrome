import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.files import write_json
from core.config import get_paths_from_config
from core.normalization import NORMALIZATION_VERSION, normalize_text, enrich_library_entry_for_dedup
from core.utils import AUDIO_EXTS, read_tags, get_file_signature

logger = logging.getLogger(__name__)

def _get_workers_per_dir() -> int:
    """Read workers-per-dir from config.json, falling back to env var then 2."""
    try:
        from core.config import load_config
        cfg = load_config()
        val = cfg.get("library_workers_per_dir")
        if val is not None:
            return max(1, int(val))
    except Exception:
        pass
    return max(1, int(os.environ.get("LIBRARY_WORKERS_PER_DIR", "2") or "2"))


def parse_filename_patterns(path: Path, scan_dirs):
    stem = path.stem.strip()
    result = {
        "parsed_artist": "",
        "parsed_title": "",
        "parsed_track_title": "",
        "stem_norm": normalize_text(stem),
        "artist_dir_norm": "",
        "album_dir_norm": "",
    }

    for base in scan_dirs:
        try:
            rel = path.relative_to(base)
            parts = rel.parts
            if len(parts) >= 2:
                result["artist_dir_norm"] = normalize_text(parts[0])
            if len(parts) >= 3:
                result["album_dir_norm"] = normalize_text(parts[1])
            break
        except Exception:
            pass

    if " - " in stem:
        left, right = stem.split(" - ", 1)
        if re.fullmatch(r"\d{1,3}", left.strip()):
            result["parsed_track_title"] = right.strip()
        else:
            result["parsed_artist"] = left.strip()
            result["parsed_title"] = right.strip()
    elif re.match(r"^\d{1,3}\s*-\s*", stem):
        result["parsed_track_title"] = re.sub(r"^\d{1,3}\s*-\s*", "", stem).strip()

    result.update(
        {
            "norm_parsed_artist": normalize_text(result["parsed_artist"]),
            "norm_parsed_title": normalize_text(result["parsed_title"]),
            "norm_parsed_track_title": normalize_text(result["parsed_track_title"]),
        }
    )
    return result


def build_library_entry(path: Path, scan_dirs):
    mtime_ns, size = get_file_signature(path)
    return _entry_from(path, read_tags(path), mtime_ns, size, scan_dirs)


def _entry_from(path: Path, tags, mtime_ns, size, scan_dirs):
    parsed = parse_filename_patterns(path, scan_dirs)
    entry = {
        "path": str(path),
        "path_str": str(path),
        "mtime_ns": mtime_ns,
        "size": size,
        "tag_artist": tags["artist"],
        "tag_title": tags["title"],
        "tag_album": tags["album"],
        "duration": tags["duration"],
        "norm_tag_artist": normalize_text(tags["artist"]),
        "norm_tag_title": normalize_text(tags["title"]),
        "norm_tag_album": normalize_text(tags["album"]),
        **parsed,
    }
    return enrich_library_entry_for_dedup(entry)


def _scan_one_dir(base: Path) -> list:
    """Scanne un seul répertoire source et retourne la liste des fichiers audio."""
    files = []
    if not base.exists():
        return files
    for root, _, filenames in os.walk(base):
        for filename in filenames:
            path = Path(root) / filename
            if path.suffix.lower() in AUDIO_EXTS:
                files.append(path)
    return files


def scan_audio_files(scan_dirs) -> list:
    """Scanne tous les répertoires sources en parallèle (un thread par répertoire)."""
    if not scan_dirs:
        return []
    if len(scan_dirs) == 1:
        return _scan_one_dir(scan_dirs[0])

    all_files = []
    with ThreadPoolExecutor(max_workers=len(scan_dirs)) as executor:
        for files in executor.map(_scan_one_dir, scan_dirs):
            all_files.extend(files)
    return all_files


def _group_files_by_dir(files: list, scan_dirs) -> dict:
    """Associe chaque fichier à son répertoire source (son HDD)."""
    groups = {d: [] for d in scan_dirs}
    unmatched = []
    for path in files:
        matched = False
        for d in scan_dirs:
            try:
                path.relative_to(d)
                groups[d].append(path)
                matched = True
                break
            except ValueError:
                continue
        if not matched:
            unmatched.append(path)
    # Les fichiers sans répertoire source connu vont dans un groupe générique
    if unmatched:
        groups[None] = unmatched
    return groups


def save_library_cache(library, library_cache_file):
    write_json(library_cache_file, {"generated_at": int(time.time()), "count": len(library), "library": library,
                                    "normalization": NORMALIZATION_VERSION})


def renormalize_cache() -> int:
    """At start: a cache made with an older normalize_text gets its keys made
    again from the tags it holds, without reading a file. Otherwise Deezer's
    side would use the new keys and the library the old ones, and nothing
    would match until a full rebuild. Returns how many entries changed."""
    with _cache_lock:
        scan_dirs, _, library_cache_file, _ = get_paths_from_config()
        try:
            payload = json.loads(library_cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        if not isinstance(payload, dict) or payload.get("normalization") == NORMALIZATION_VERSION:
            return 0
        library = []
        for old in payload.get("library") or []:
            if not isinstance(old, dict) or not old.get("path"):
                continue
            tags = {"artist": old.get("tag_artist") or "", "title": old.get("tag_title") or "",
                    "album": old.get("tag_album") or "", "duration": old.get("duration")}
            library.append(_entry_from(Path(old["path"]), tags, old.get("mtime_ns"), old.get("size"), scan_dirs))
        save_library_cache(library, library_cache_file)
        return len(library)


def load_library_cache(library_cache_file):
    if not library_cache_file.exists():
        return []
    try:
        data = json.loads(library_cache_file.read_text(encoding="utf-8"))
        return data.get("library", [])
    except Exception:
        return []


_snapshot = {"key": None, "value": None}
_snapshot_lock = threading.Lock()


def library_snapshot():
    """The library index as the web pages use it: entries, a matching index,
    search labels and counters. Rebuilt only when the cache file changes."""
    from core.matching import LibraryIndex

    _, _, library_cache_file, _ = get_paths_from_config()
    try:
        stat = library_cache_file.stat()
        key = (str(library_cache_file), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (str(library_cache_file), None, None)

    with _snapshot_lock:
        if _snapshot["key"] == key:
            return _snapshot["value"]

        generated_at = None
        library = []
        if key[1] is not None:
            try:
                data = json.loads(library_cache_file.read_text(encoding="utf-8"))
                library = data.get("library", []) if isinstance(data, dict) else []
                generated_at = data.get("generated_at") if isinstance(data, dict) else None
            except Exception:
                library = []

        artists, albums, labels = set(), set(), []
        for entry in library:
            artist = entry.get("tag_artist") or entry.get("parsed_artist") or ""
            title = entry.get("tag_title") or entry.get("parsed_title") or entry.get("parsed_track_title") or Path(entry["path"]).stem
            album = entry.get("tag_album") or ""
            labels.append(normalize_text(f"{artist} {title} {album}"))
            norm_artist = normalize_text(artist) or entry.get("artist_dir_norm") or ""
            norm_album = normalize_text(album) or entry.get("album_dir_norm") or ""
            if norm_artist:
                artists.add(norm_artist)
                if norm_album:
                    albums.add((norm_artist, norm_album))

        value = {
            "library": library,
            "index": LibraryIndex(library),
            "labels": labels,
            "by_path": {e["path"]: e for e in library},
            "meta": {"count": len(library), "artists": len(artists), "albums": len(albums), "generated_at": generated_at},
        }
        _snapshot["key"] = key
        _snapshot["value"] = value
        return value


def describe_entry(entry):
    """Short public view of a library entry for the browser."""
    path = Path(entry["path"])
    return {
        "path": entry["path"],
        "artist": entry.get("tag_artist") or entry.get("parsed_artist") or "",
        "title": entry.get("tag_title") or entry.get("parsed_title") or entry.get("parsed_track_title") or path.stem,
        "album": entry.get("tag_album") or "",
        "duration": entry.get("duration"),
        "file": path.name,
    }


def search_library(query: str, limit: int = 20):
    snap = library_snapshot()
    needle = normalize_text(query)
    if not needle:
        return []
    try:
        from rapidfuzz import fuzz, process

        hits = process.extract(needle, snap["labels"], scorer=fuzz.WRatio, limit=limit, score_cutoff=72)
        found = [(i, score) for _, score, i in hits]
    except ImportError:
        words = needle.split()
        scored = [(i, sum(w in label for w in words) / len(words) * 100) for i, label in enumerate(snap["labels"])]
        found = sorted((x for x in scored if x[1] >= 50), key=lambda x: -x[1])[:limit]
    return [{**describe_entry(snap["library"][i]), "score": round(score)} for i, score in found]


def _process_dir_into(scan_dir, dir_files, scan_dirs, library, lock, counter,
                      total, emit_fn=None, progress_interval=50):
    """
    Traite les fichiers d'un répertoire source avec son propre pool de threads.
    Écrit les résultats dans `library` (liste partagée, protégée par `lock`).
    `counter` est une liste à un élément [int] servant de compteur partagé.
    """
    with ThreadPoolExecutor(max_workers=_get_workers_per_dir()) as executor:
        futures = {executor.submit(build_library_entry, p, scan_dirs): p for p in dir_files}
        for future in as_completed(futures):
            entry = None
            try:
                entry = future.result()
            except Exception:
                pass

            with lock:
                if entry is not None:
                    library.append(entry)
                counter[0] += 1
                current = counter[0]

            if emit_fn and (current % progress_interval == 0 or current == total):
                emit_fn(
                    f"Library scan: {current}/{total}",
                    stage="cache",
                    progress=round((current / total) * 100) if total else 100,
                )


# One rebuild or refresh at a time: two at once would each save their own list,
# and the slower one would lose what the other found.
_cache_lock = threading.Lock()


def _emitter(progress_cb):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)
    return emit


def _build_entries(files, scan_dirs, emit=None) -> list:
    """The cache entries of these files: one thread per source folder (one disk),
    each with its own pool."""
    files_by_dir = _group_files_by_dir(files, scan_dirs)
    total = sum(len(v) for v in files_by_dir.values())
    entries, lock, counter = [], threading.Lock(), [0]
    threads = [
        threading.Thread(target=_process_dir_into, args=(d, dir_files, scan_dirs, entries, lock, counter, total, emit),
                         daemon=True)
        for d, dir_files in files_by_dir.items()
        if dir_files
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return entries


def rebuild_library_cache_full():
    return rebuild_library_cache_full_with_progress()


def rebuild_library_cache_full_with_progress(progress_cb=None):
    emit = _emitter(progress_cb)
    with _cache_lock:
        scan_dirs, _, library_cache_file, _ = get_paths_from_config()
        emit("Scanning source directories…", stage="cache", progress=0)
        files = scan_audio_files(scan_dirs)
        emit(f"Scan complete: {len(files)} files found", stage="cache", progress=0)
        if not files:
            save_library_cache([], library_cache_file)
            emit("Library cache rebuilt (0 files)", stage="cache", progress=100)
            return {"count": 0}
        library = _build_entries(files, scan_dirs, emit)
        emit("Sorting and writing cache…", stage="cache", progress=99)
        library.sort(key=lambda x: x["path_str"])
        save_library_cache(library, library_cache_file)
        emit("Library cache rebuilt", stage="cache", progress=100)
        return {"count": len(library)}


def _inside(path_str, folder) -> bool:
    try:
        Path(path_str).relative_to(folder)
        return True
    except ValueError:
        return False


def _absent_folders(scan_dirs, files, old_library) -> list:
    """Source folders that gave no file although the cache had some: a disk not
    mounted at that moment (its mount point is then missing, or empty), more
    likely than every file of it deleted. Their entries are kept."""
    absent = []
    for folder in scan_dirs:
        found = any(_inside(str(f), folder) for f in files)
        if not found and any(_inside(e["path_str"], folder) for e in old_library):
            logger.warning("No file found in %s, which had some: kept as it was (not mounted?)", folder)
            absent.append(folder)
    return absent


def refresh_library_cache_incremental():
    return refresh_library_cache_incremental_with_progress()


def refresh_library_cache_incremental_with_progress(progress_cb=None):
    emit = _emitter(progress_cb)
    with _cache_lock:
        scan_dirs, _, library_cache_file, _ = get_paths_from_config()
        old_library = load_library_cache(library_cache_file)
        old_index = {entry["path_str"]: entry for entry in old_library}

        emit("Scanning existing files…", stage="cache", progress=0)
        current_files = scan_audio_files(scan_dirs)
        absent = _absent_folders(scan_dirs, current_files, old_library)
        kept = [e for e in old_library if any(_inside(e["path_str"], folder) for folder in absent)]

        reused = []
        changed = []
        for path in current_files:
            try:
                mtime_ns, size = get_file_signature(path)
            except FileNotFoundError:
                continue
            old = old_index.get(str(path))
            if old and old.get("mtime_ns") == mtime_ns and old.get("size") == size:
                reused.append(old)
            else:
                changed.append(path)

        emit(f"Processing {len(changed)} changed files", stage="cache", progress=0)
        rebuilt = _build_entries(changed, scan_dirs, emit) if changed else []

        new_library = sorted({e["path_str"]: e for e in kept + reused + rebuilt}.values(), key=lambda x: x["path_str"])
        save_library_cache(new_library, library_cache_file)
        emit("Incremental cache updated", stage="cache", progress=100)
        return {"count": len(new_library), "reused": len(reused) + len(kept), "rebuilt": len(rebuilt)}
