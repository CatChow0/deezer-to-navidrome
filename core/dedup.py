import json
import shutil
import time
import uuid
from collections import defaultdict
from pathlib import Path

from core.config import (
    DEDUP_CHOICES_FILE,
    DEDUP_QUARANTINE_DIR,
    DEDUP_REPORT_FILE,
    ensure_dirs,
    get_paths_from_config,
)
from core.library import load_library_cache, rebuild_library_cache_full_with_progress
from core.normalization import (
    enrich_library_entry_for_dedup,
    get_duration_bucket,
    normalize_group_identity,
    normalize_entry,
    normalize_text,
    safe_list,
    safe_dict,
    should_group_as_duplicates,
)


def choose_keeper(entries):
    clean_entries = [normalize_entry(e) for e in safe_list(entries) if safe_dict(e)]
    if not clean_entries:
        return {}
    ranked = sorted(
        clean_entries,
        key=lambda e: (
            e.get("quality_score", 0) or 0,
            e.get("duration", 0) or 0,
            e.get("path_str", ""),
        ),
        reverse=True,
    )
    return ranked[0]


def load_dedup_choices():
    if not DEDUP_CHOICES_FILE.exists():
        return {}
    try:
        data = json.loads(DEDUP_CHOICES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_dedup_choices(choices):
    ensure_dirs()
    DEDUP_CHOICES_FILE.write_text(
        json.dumps(choices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dedup_entry_fingerprint(entry):
    return "|".join([
        normalize_text(entry.get("path_str") or entry.get("path") or ""),
        normalize_text(entry.get("artist_norm_strict") or entry.get("norm_tag_artist") or ""),
        normalize_text(entry.get("base_title") or entry.get("norm_tag_title") or entry.get("stem_norm") or ""),
        str(get_duration_bucket(entry.get("duration"), 2) or ""),
    ])


def dedup_group_key(group):
    identity = group.get("identity") or {}
    return "|".join([
        normalize_text(identity.get("artist") or ""),
        normalize_text(identity.get("album") or ""),
        normalize_text(identity.get("base_title") or ""),
        ",".join(identity.get("version_flags") or []),
    ])


def group_entries_by_folder(entries):
    folders = defaultdict(list)
    for e in entries:
        p = Path(e.get("path_str") or e.get("path") or "")
        folder = str(p.parent)
        folders[folder].append(e)
    return folders


def build_dedup_groups(library):
    enriched = []
    for item in safe_list(library):
        if not isinstance(item, dict):
            continue
        try:
            enriched.append(enrich_library_entry_for_dedup(item))
        except Exception:
            continue

    buckets = defaultdict(list)
    for entry in enriched:
        entry = normalize_entry(entry)
        artist_key = entry.get("artist_norm_strict") or entry.get("tag_artist") or entry.get("artist_dir_norm") or ""
        title_key = entry.get("base_title") or entry.get("tag_title") or entry.get("parsed_track_title") or entry.get("stem_norm") or ""
        buckets[(artist_key, title_key)].append(entry)

    groups = []
    rejected_pairs = []

    for bucket_entries in buckets.values():
        bucket_entries = [normalize_entry(e) for e in safe_list(bucket_entries)]
        bucket_entries = [e for e in bucket_entries if e.get("path_str")]

        if len(bucket_entries) < 2:
            continue

        consumed = set()

        for i, entry in enumerate(bucket_entries):
            if i in consumed:
                continue

            cluster = [entry]
            consumed.add(i)

            for j in range(i + 1, len(bucket_entries)):
                if j in consumed:
                    continue

                other = bucket_entries[j]
                try:
                    ok, reason = should_group_as_duplicates(entry, other)
                except Exception as e:
                    ok, reason = False, f"compare_error:{e}"

                if ok:
                    cluster.append(other)
                    consumed.add(j)
                else:
                    rejected_pairs.append({
                        "left": entry.get("path_str", ""),
                        "right": other.get("path_str", ""),
                        "reason": reason,
                    })

            if len(cluster) < 2:
                continue

            keeper = normalize_entry(choose_keeper(cluster))
            if not keeper.get("path_str"):
                continue

            duplicates = [
                normalize_entry(x)
                for x in cluster
                if normalize_entry(x).get("path_str") != keeper.get("path_str")
            ]

            group_identity = normalize_group_identity({
                "artist": keeper.get("artist_norm_strict") or keeper.get("tag_artist") or keeper.get("artist_dir_norm") or "",
                "album": keeper.get("album_norm_strict") or keeper.get("tag_album") or keeper.get("album_dir_norm") or "",
                "base_title": keeper.get("base_title") or keeper.get("tag_title") or keeper.get("parsed_track_title") or keeper.get("stem_norm") or "",
                "version_flags": keeper.get("version_flags", []),
            })

            folders_map = defaultdict(list)
            for entry_item in [keeper] + duplicates:
                path_str = entry_item.get("path_str", "")
                folder = str(Path(path_str).parent) if path_str else ""
                folders_map[folder].append(entry_item)

            folders = []
            for folder_name, folder_entries in sorted(folders_map.items(), key=lambda x: x[0]):
                folders.append({
                    "folder": folder_name,
                    "keep_by_default": any(e.get("path_str") == keeper.get("path_str") for e in folder_entries),
                    "entries": [
                        {
                            "path_str": e.get("path_str", ""),
                            "tag_artist": e.get("tag_artist", ""),
                            "tag_title": e.get("tag_title", ""),
                            "tag_album": e.get("tag_album", ""),
                            "parsed_artist": e.get("parsed_artist", ""),
                            "parsed_title": e.get("parsed_title", ""),
                            "parsed_track_title": e.get("parsed_track_title", ""),
                            "stem_norm": e.get("stem_norm", ""),
                            "album_dir_norm": e.get("album_dir_norm", ""),
                            "artist_dir_norm": e.get("artist_dir_norm", ""),
                            "track_number": e.get("track_number"),
                            "duration": e.get("duration"),
                            "size": e.get("size", 0),
                            "quality_score": e.get("quality_score", 0),
                        }
                        for e in sorted(folder_entries, key=lambda x: x.get("path_str", ""))
                    ],
                })

            groups.append({
                "group_id": str(uuid.uuid4()),
                "identity": group_identity,
                "count": len(cluster),
                "keeper": {
                    "path_str": keeper.get("path_str", ""),
                    "tag_artist": keeper.get("tag_artist", ""),
                    "tag_title": keeper.get("tag_title", ""),
                    "tag_album": keeper.get("tag_album", ""),
                    "parsed_artist": keeper.get("parsed_artist", ""),
                    "parsed_title": keeper.get("parsed_title", ""),
                    "parsed_track_title": keeper.get("parsed_track_title", ""),
                    "stem_norm": keeper.get("stem_norm", ""),
                    "album_dir_norm": keeper.get("album_dir_norm", ""),
                    "artist_dir_norm": keeper.get("artist_dir_norm", ""),
                    "track_number": keeper.get("track_number"),
                    "duration": keeper.get("duration"),
                    "quality_score": keeper.get("quality_score", 0),
                    "version_flags": keeper.get("version_flags", []),
                },
                "duplicates": duplicates,
                "entries": [keeper] + duplicates,
                "folders": folders,
            })

    groups.sort(
        key=lambda g: (
            -(g.get("count") or 0),
            g.get("identity", {}).get("artist", ""),
            g.get("identity", {}).get("base_title", ""),
        )
    )

    return groups, rejected_pairs


def group_dedup_groups_by_album(groups):
    albums = {}

    for group in safe_list(groups):
        if not isinstance(group, dict):
            continue
        identity = group.get("identity") or {}
        artist = identity.get("artist") or ""
        album = identity.get("album") or ""
        album_key = (artist, album)

        if album_key not in albums:
            albums[album_key] = {"artist": artist, "album": album, "tracks": []}
        albums[album_key]["tracks"].append(group)

    for album_key in albums:
        albums[album_key]["tracks"].sort(
            key=lambda g: g.get("identity", {}).get("base_title", "")
        )

    return sorted(
        [{"key": k, **v} for k, v in albums.items()],
        key=lambda a: (a["artist"], a["album"])
    )


def filter_and_preselect_dedup_groups(groups):
    existing_choices = load_dedup_choices() or {}
    keeper_hints = {}
    filtered = []

    for group in safe_list(groups):
        if not isinstance(group, dict):
            continue

        group_key = dedup_group_key(group)
        group_id = group.get("group_id")

        if group_key in existing_choices:
            choice_record = existing_choices[group_key]
            previous_keep_paths = set(choice_record.get("keep_paths", []))

            current_paths = set()
            for entry in safe_list(group.get("entries")):
                if isinstance(entry, dict):
                    path = entry.get("path_str")
                    if path:
                        current_paths.add(path)

            new_paths = current_paths - previous_keep_paths

            if not new_paths:
                continue
            else:
                keeper_hints[group_id] = list(previous_keep_paths)
                filtered.append(group)
        else:
            filtered.append(group)

    return filtered, keeper_hints


def save_dedup_report(report):
    ensure_dirs()
    DEDUP_REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_dedup_report():
    if not DEDUP_REPORT_FILE.exists():
        return None
    try:
        return json.loads(DEDUP_REPORT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_dedup_analysis(progress_cb=None):
    def emit(message=None, progress=None, stage=None, payload=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage, payload=payload)

    _, _, library_cache_file, _ = get_paths_from_config()
    library = load_library_cache(library_cache_file) or []

    if not library:
        emit("Cache missing, running full rebuild", 0, "cache")
        rebuild_library_cache_full_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: emit(
                message=message, progress=progress, stage=stage
            )
        )
        library = load_library_cache(library_cache_file) or []

    emit("Running advanced duplicate analysis", 10, "dedup")

    try:
        groups, rejected_pairs = build_dedup_groups(library)
    except Exception as e:
        emit(f"Dedup error: {e}", 100, "error")
        raise

    filtered_groups, keeper_hints = filter_and_preselect_dedup_groups(groups)
    album_groups = group_dedup_groups_by_album(filtered_groups)

    report = {
        "generated_at": int(time.time()),
        "group_count": len(filtered_groups),
        "total_group_count": len(groups),
        "duplicate_file_count": sum(len(g.get("duplicates", [])) for g in filtered_groups),
        "album_groups": album_groups,
        "groups": filtered_groups,
        "keeper_hints": keeper_hints,
        "rejected_pairs": rejected_pairs[:1000],
    }

    save_dedup_report(report)

    emit(
        message=f"Analysis done: {len(filtered_groups)} group(s) to review, {len(groups) - len(filtered_groups)} already validated, {report['duplicate_file_count']} duplicate candidates",
        progress=100,
        stage="dedup_done",
        payload={
            "group_count": len(filtered_groups),
            "duplicate_file_count": report["duplicate_file_count"],
        },
    )
    return report


def ensure_quarantine_dir():
    DEDUP_QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)


def quarantine_file(path_str: str):
    ensure_quarantine_dir()
    src = Path(path_str)
    if not src.exists():
        return {"path": path_str, "status": "missing"}

    target = DEDUP_QUARANTINE_DIR / src.name
    suffix = 1
    while target.exists():
        target = DEDUP_QUARANTINE_DIR / f"{src.stem}__{suffix}{src.suffix}"
        suffix += 1

    shutil.move(str(src), str(target))
    return {"path": path_str, "status": "moved", "target": str(target)}


def apply_dedup_decisions(decisions, mode="quarantine"):
    report = load_dedup_report()
    if not isinstance(report, dict):
        raise RuntimeError("Aucun dedup_report disponible")

    groups_by_id = {
        g.get("group_id"): g
        for g in safe_list(report.get("groups"))
        if isinstance(g, dict) and g.get("group_id")
    }

    results = []

    for decision in safe_list(decisions):
        if not isinstance(decision, dict):
            continue

        group_id = decision.get("group_id")
        keep_paths = set(str(p) for p in safe_list(decision.get("keep_paths")))
        group = groups_by_id.get(group_id)
        if not isinstance(group, dict):
            continue

        entries = safe_list(group.get("entries"))
        delete_candidates = [
            e for e in entries
            if isinstance(e, dict) and e.get("path_str") and e.get("path_str") not in keep_paths
        ]

        for entry in delete_candidates:
            path_str = entry.get("path_str")
            if not path_str:
                continue

            if mode == "quarantine":
                results.append(quarantine_file(path_str))
            elif mode == "delete":
                p = Path(path_str)
                if p.exists():
                    p.unlink()
                    results.append({"path": path_str, "status": "deleted"})
                else:
                    results.append({"path": path_str, "status": "missing"})
            else:
                raise RuntimeError(f"Mode inconnu: {mode}")

    existing_choices = load_dedup_choices() or {}
    groups_by_id = {g.get("group_id"): g for g in safe_list(report.get("groups"))}

    for decision in safe_list(decisions):
        group_id = decision.get("group_id")
        keep_paths = set(str(p) for p in safe_list(decision.get("keep_paths")))
        group = groups_by_id.get(group_id)
        if not group:
            continue

        group_key = dedup_group_key(group)

        if group_key not in existing_choices:
            existing_choices[group_key] = {
                "identity": group.get("identity", {}),
                "keep_paths": []
            }

        existing_paths = set(existing_choices[group_key].get("keep_paths", []))
        existing_paths.update(keep_paths)
        existing_choices[group_key]["keep_paths"] = list(existing_paths)

    save_dedup_choices(existing_choices)

    return {"processed": len(results), "results": results}
