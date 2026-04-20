import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.config import get_paths_from_config
from core.normalization import normalize_text, enrich_library_entry_for_dedup
from core.utils import AUDIO_EXTS, read_tags, get_file_signature

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
    tags = read_tags(path)
    parsed = parse_filename_patterns(path, scan_dirs)
    mtime_ns, size = get_file_signature(path)

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
    """Sauvegarde atomique : écriture dans un fichier temp puis renommage."""
    payload = {
        "generated_at": int(time.time()),
        "count": len(library),
        "library": library,
    }
    library_cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = library_cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(library_cache_file)


def load_library_cache(library_cache_file):
    if not library_cache_file.exists():
        return []
    try:
        data = json.loads(library_cache_file.read_text(encoding="utf-8"))
        return data.get("library", [])
    except Exception:
        return []


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


def rebuild_library_cache_full():
    scan_dirs, _, library_cache_file, _ = get_paths_from_config()

    files_by_dir = _group_files_by_dir(scan_audio_files(scan_dirs), scan_dirs)
    total = sum(len(v) for v in files_by_dir.values())

    library = []
    lock = threading.Lock()
    counter = [0]

    threads = [
        threading.Thread(
            target=_process_dir_into,
            args=(d, files, scan_dirs, library, lock, counter, total),
            daemon=True,
        )
        for d, files in files_by_dir.items()
        if files
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    library.sort(key=lambda x: x["path_str"])
    save_library_cache(library, library_cache_file)
    return {"count": len(library)}


def rebuild_library_cache_full_with_progress(progress_cb=None):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)

    scan_dirs, _, library_cache_file, _ = get_paths_from_config()

    emit("Scanning source directories…", stage="cache", progress=0)

    # Scan parallèle : un thread par HDD
    files_by_dir = _group_files_by_dir(scan_audio_files(scan_dirs), scan_dirs)
    total = sum(len(v) for v in files_by_dir.values())

    emit(f"Scan complete: {total} files found", stage="cache", progress=0)

    if not total:
        save_library_cache([], library_cache_file)
        emit("Library cache rebuilt (0 files)", stage="cache", progress=100)
        return {"count": 0}

    library = []
    lock = threading.Lock()
    counter = [0]

    # Un thread par répertoire source (= par HDD), chacun avec son pool interne
    threads = [
        threading.Thread(
            target=_process_dir_into,
            args=(d, files, scan_dirs, library, lock, counter, total, emit),
            daemon=True,
        )
        for d, files in files_by_dir.items()
        if files
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    emit("Sorting and writing cache…", stage="cache", progress=99)
    library.sort(key=lambda x: x["path_str"])
    save_library_cache(library, library_cache_file)
    emit("Library cache rebuilt", stage="cache", progress=100)
    return {"count": len(library)}


def refresh_library_cache_incremental():
    scan_dirs, _, library_cache_file, _ = get_paths_from_config()
    old_library = load_library_cache(library_cache_file)
    old_index = {entry["path_str"]: entry for entry in old_library}
    current_files = scan_audio_files(scan_dirs)
    current_paths = {str(p): p for p in current_files}

    reused = []
    changed = []

    for path_str, path in current_paths.items():
        try:
            mtime_ns, size = get_file_signature(path)
        except FileNotFoundError:
            continue
        old = old_index.get(path_str)
        if old and old.get("mtime_ns") == mtime_ns and old.get("size") == size:
            reused.append(old)
        else:
            changed.append(path)

    files_by_dir = _group_files_by_dir(changed, scan_dirs)
    total = len(changed)

    rebuilt = []
    lock = threading.Lock()
    counter = [0]

    threads = [
        threading.Thread(
            target=_process_dir_into,
            args=(d, files, scan_dirs, rebuilt, lock, counter, total),
            daemon=True,
        )
        for d, files in files_by_dir.items()
        if files
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    new_library = sorted(reused + rebuilt, key=lambda x: x["path_str"])
    save_library_cache(new_library, library_cache_file)
    return {"count": len(new_library), "reused": len(reused), "rebuilt": len(rebuilt)}


def refresh_library_cache_incremental_with_progress(progress_cb=None):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)

    scan_dirs, _, library_cache_file, _ = get_paths_from_config()
    old_library = load_library_cache(library_cache_file)
    old_index = {entry["path_str"]: entry for entry in old_library}

    emit("Scanning existing files…", stage="cache", progress=0)
    current_files = scan_audio_files(scan_dirs)
    current_paths = {str(p): p for p in current_files}

    reused = []
    changed = []

    for path_str, path in current_paths.items():
        try:
            mtime_ns, size = get_file_signature(path)
        except FileNotFoundError:
            continue
        old = old_index.get(path_str)
        if old and old.get("mtime_ns") == mtime_ns and old.get("size") == size:
            reused.append(old)
        else:
            changed.append(path)

    total = len(changed)
    emit(f"Processing {total} changed files", stage="cache", progress=0)

    rebuilt = []

    if total:
        files_by_dir = _group_files_by_dir(changed, scan_dirs)
        lock = threading.Lock()
        counter = [0]

        threads = [
            threading.Thread(
                target=_process_dir_into,
                args=(d, files, scan_dirs, rebuilt, lock, counter, total, emit),
                daemon=True,
            )
            for d, files in files_by_dir.items()
            if files
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    new_library = sorted(reused + rebuilt, key=lambda x: x["path_str"])
    save_library_cache(new_library, library_cache_file)
    emit("Incremental cache updated", stage="cache", progress=100)
    return {"count": len(new_library), "reused": len(reused), "rebuilt": len(rebuilt)}
