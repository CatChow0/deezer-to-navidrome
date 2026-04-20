#!/usr/bin/env python3
import json
import os
import re
import time
import unicodedata
import uuid
import threading
from difflib import SequenceMatcher
from pathlib import Path
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import ast
from collections import defaultdict
import shutil

import requests
from flask import (
    Flask,
    render_template,
    request,
    Response,
    redirect,
    url_for,
    flash,
    jsonify,
    send_from_directory,
)
from mutagen import File as MutagenFile

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
COVERS_DIR = DATA_DIR / "covers"
CONFIG_FILE = DATA_DIR / "config.json"
PLAYLIST_IDS_FILE = DATA_DIR / "deezer_playlist_ids.json"
LIBRARY_CACHE_FILE = DATA_DIR / "music_library_cache.json"
PREVIEW_STATE_FILE = DATA_DIR / "playlist_preview_state.json"
DEDUP_REPORT_FILE = DATA_DIR / "dedup_report.json"
DEDUP_QUARANTINE_DIR = DATA_DIR / "dedup_quarantine"
DEDUP_CHOICES_FILE = DATA_DIR / "dedup_choices.json"


def get_app_version():
    """Read version from VERSION file or return 'unknown'."""
    try:
        version_file = Path(__file__).parent / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    return "unknown"


VERSION_CHECK_CACHE = {
    "latest_version": None,
    "latest_url": None,
    "cached_at": None,
}


def fetch_latest_github_release():
    """Fetch the latest release version from GitHub."""
    try:
        resp = requests.get(
            "https://api.github.com/repos/CatChow0/deezer-to-navidrome/releases/latest",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        version = data.get("tag_name", "").lstrip("v")
        url = data.get("html_url", "")
        return version if version else None, url
    except Exception:
        return None, None


def fetch_latest_docker_tag():
    """Fetch the latest Docker image tag (semantic versions only, excludes 'latest')."""
    try:
        resp = requests.get(
            "https://hub.docker.com/v2/repositories/catchow/deezer-to-navidrome/tags?page_size=25",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        semver_tags = []
        for r in results:
            name = r.get("name", "")
            parts = name.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                semver_tags.append(name)
        if semver_tags:
            semver_tags.sort(key=lambda v: [int(x) for x in v.split(".")], reverse=True)
            return semver_tags[0], "https://hub.docker.com/r/catchow/deezer-to-navidrome/tags"
        return None, None
    except Exception:
        return None, None


def compare_versions(v1, v2):
    """Compare two semantic versions. Returns True if v1 < v2."""
    try:
        parts1 = [int(x) for x in v1.split("-")[0].split(".")]
        parts2 = [int(x) for x in v2.split("-")[0].split(".")]
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))
        return parts1 < parts2
    except Exception:
        return False


def get_latest_available_version():
    """Get the latest available version from GitHub and Docker Hub with caching."""
    now = time.time()
    cache_duration = 3600  # 1 hour

    # Return cached value if fresh
    if (
        VERSION_CHECK_CACHE["cached_at"]
        and now - VERSION_CHECK_CACHE["cached_at"] < cache_duration
        and VERSION_CHECK_CACHE["latest_version"]
    ):
        return {
            "version": VERSION_CHECK_CACHE["latest_version"],
            "url": VERSION_CHECK_CACHE["latest_url"],
            "source": "cached",
        }

    current_version = get_app_version()
    latest_version = None
    latest_url = None
    source = None

    # Try GitHub first
    gh_version, gh_url = fetch_latest_github_release()
    if gh_version and compare_versions(current_version, gh_version):
        latest_version = gh_version
        latest_url = gh_url
        source = "github"

    # Try Docker Hub if GitHub didn't yield a newer version
    if not latest_version:
        docker_version, docker_url = fetch_latest_docker_tag()
        if docker_version and compare_versions(current_version, docker_version):
            latest_version = docker_version
            latest_url = docker_url
            source = "docker"

    # Update cache
    VERSION_CHECK_CACHE["latest_version"] = latest_version
    VERSION_CHECK_CACHE["latest_url"] = latest_url
    VERSION_CHECK_CACHE["cached_at"] = now

    result = {"version": latest_version, "url": latest_url, "source": source}
    return result


VERSION_KEYWORDS = {
    "instrumental": ["instrumental", "instr"],
    "acapella": ["acapella", "a cappella"],
    "remix": ["remix", "rmx", "mix"],
    "live": ["live"],
    "demo": ["demo"],
    "session": ["session", "garage session", "studio session"],
    "radio_edit": ["radio edit"],
    "extended": ["extended", "extended mix"],
    "edit": ["edit"],
    "mono": ["mono"],
    "stereo": ["stereo"],
    "clean": ["clean"],
    "explicit": ["explicit"],
    "original": ["original", "original version", "original mix"],
    "bonus": ["bonus", "bonus track"],
    "alt": ["alternate", "alt version", "alternative"],
    "remaster": ["remaster", "remastered"],
}


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"\bfeat\.?\b", " feat ", s)
    s = re.sub(r"\bft\.?\b", " feat ", s)
    s = re.sub(r"\bfeaturing\b", " feat ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(
        r"\b(remaster(ed)?|radio edit|explicit|clean|mono|stereo|version)\b", " ", s
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_album_strict(s: str) -> str:
    s = normalize_text(s)
    s = re.sub(
        r"\b(deluxe|expanded|complete|anniversary|collector s edition|edition)\b",
        " ",
        s,
    )
    s = re.sub(r"\b(cd|disc|digital media)\s*\d+\b", " ", s)
    s = re.sub(r"\b\d{4}\b", " ", s)
    return normalize_spaces(s)


def extract_track_number_from_path(path: str):
    name = Path(path).stem
    m = re.search(r"(?:^|\D)(\d{1,2})(?:\D|$)", name)
    return int(m.group(1)) if m else None


def extract_version_flags(*values):
    raw = " ".join([v for v in values if v])
    normalized = normalize_text(raw)
    found = set()
    for key, needles in VERSION_KEYWORDS.items():
        for needle in needles:
            if normalize_text(needle) in normalized:
                found.add(key)
                break
    return sorted(found)


def strip_version_tokens(title: str) -> str:
    s = normalize_text(title)
    for needles in VERSION_KEYWORDS.values():
        for needle in needles:
            s = re.sub(rf"\b{re.escape(normalize_text(needle))}\b", " ", s)
    s = re.sub(r"\b(version|mix)\b", " ", s)
    return normalize_spaces(s)


def audio_extension_rank(path: str) -> int:
    ext = Path(path).suffix.lower()
    order = {
        ".flac": 100,
        ".wav": 95,
        ".wv": 92,
        ".m4a": 80,
        ".opus": 70,
        ".ogg": 65,
        ".mp3": 60,
        ".aac": 55,
        ".mp4": 50,
    }
    return order.get(ext, 0)


def compute_quality_score(entry):
    score = 0.0
    score += audio_extension_rank(entry.get("path", ""))
    score += min((entry.get("size") or 0) / 1024 / 1024, 200)
    if entry.get("tag_artist"):
        score += 6
    if entry.get("tag_title"):
        score += 6
    if entry.get("tag_album"):
        score += 4
    if entry.get("duration"):
        score += 3
    return round(score, 2)


def enrich_library_entry_for_dedup(entry):
    title_source = (
        entry.get("tag_title")
        or entry.get("parsed_track_title")
        or entry.get("parsed_title")
        or Path(entry.get("path", "")).stem
    )
    album_source = entry.get("tag_album") or entry.get("album_dir_norm") or ""
    artist_source = (
        entry.get("tag_artist")
        or entry.get("parsed_artist")
        or entry.get("artist_dir_norm")
        or ""
    )

    version_flags = extract_version_flags(
        entry.get("tag_title", ""),
        entry.get("parsed_title", ""),
        entry.get("parsed_track_title", ""),
        Path(entry.get("path", "")).stem,
    )

    track_number = extract_track_number_from_path(entry.get("path", ""))
    base_title = strip_version_tokens(title_source)
    album_norm_strict = normalize_album_strict(album_source)
    artist_norm_strict = normalize_text(artist_source)

    enriched = dict(entry)
    enriched.update(
        {
            "base_title": base_title,
            "album_norm_strict": album_norm_strict,
            "artist_norm_strict": artist_norm_strict,
            "version_flags": version_flags,
            "track_number": track_number,
            "quality_score": compute_quality_score(entry),
        }
    )
    return enriched


def version_flags_match(a, b):
    sa = set(a or [])
    sb = set(b or [])
    return sa == sb


def duration_close(a, b, tolerance=2.0):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tolerance


def should_group_as_duplicates(a, b):
    if a.get("artist_norm_strict") and b.get("artist_norm_strict"):
        if a["artist_norm_strict"] != b["artist_norm_strict"]:
            return False, "different_artist"

    if a.get("base_title") != b.get("base_title"):
        return False, "different_base_title"

    if not version_flags_match(a.get("version_flags"), b.get("version_flags")):
        return False, "different_version_flags"

    a_album = a.get("album_norm_strict") or ""
    b_album = b.get("album_norm_strict") or ""
    if a_album and b_album and a_album != b_album:
        return False, "different_album"

    a_track = a.get("track_number")
    b_track = b.get("track_number")
    if a_album and b_album and a_album == b_album and a_track and b_track and a_track != b_track:
        return False, "different_track_number_same_album"

    if a.get("duration") is not None and b.get("duration") is not None:
        if not duration_close(a.get("duration"), b.get("duration"), tolerance=2.0):
            return False, "different_duration"

    return True, "strict_match"

def safe_dict(value):
    return value if isinstance(value, dict) else {}

def safe_list(value):
    return value if isinstance(value, list) else []

def normalize_group_identity(identity):
    identity = safe_dict(identity)
    return {
        "artist": identity.get("artist") or "",
        "album": identity.get("album") or "",
        "base_title": identity.get("base_title") or "",
        "version_flags": safe_list(identity.get("version_flags")),
    }

def normalize_entry(entry):
    entry = safe_dict(entry)
    return {
        "path_str": entry.get("path_str") or entry.get("path") or "",
        "tag_artist": entry.get("tag_artist") or "",
        "tag_title": entry.get("tag_title") or "",
        "tag_album": entry.get("tag_album") or "",
        "parsed_artist": entry.get("parsed_artist") or "",
        "parsed_title": entry.get("parsed_title") or "",
        "parsed_track_title": entry.get("parsed_track_title") or "",
        "stem_norm": entry.get("stem_norm") or "",
        "album_dir_norm": entry.get("album_dir_norm") or "",
        "artist_dir_norm": entry.get("artist_dir_norm") or "",
        "track_number": entry.get("track_number"),
        "duration": entry.get("duration"),
        "quality_score": entry.get("quality_score", 0),
        "version_flags": safe_list(entry.get("version_flags")),
    }


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
    """Regroupe les groupes de chansons par (artiste, album)."""
    albums = {}

    for group in safe_list(groups):
        if not isinstance(group, dict):
            continue
        identity = group.get("identity") or {}
        artist = identity.get("artist") or ""
        album = identity.get("album") or ""
        album_key = (artist, album)

        if album_key not in albums:
            albums[album_key] = {
                "artist": artist,
                "album": album,
                "tracks": []
            }
        albums[album_key]["tracks"].append(group)

    # Trier les tracks par base_title dans chaque album
    for album_key in albums:
        albums[album_key]["tracks"].sort(
            key=lambda g: g.get("identity", {}).get("base_title", "")
        )

    # Retourner trié par (artist, album)
    return sorted(
        [{"key": k, **v} for k, v in albums.items()],
        key=lambda a: (a["artist"], a["album"])
    )


def filter_and_preselect_dedup_groups(groups):
    """
    Filtre les groupes basés sur les choix précédents.

    Logique:
    - Si TOUS les fichiers actuels sont dans keep_paths précédents → ignorer
    - Si des NOUVEAUX fichiers existent → garder et pré-marquer les anciens

    Returns:
        (filtered_groups, keeper_hints)
        - filtered_groups: groupes à afficher
        - keeper_hints: {group_id: [keep_paths]} pour pré-cocher au frontend
    """
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

            # Tous les fichiers actuels
            current_paths = set()
            for entry in safe_list(group.get("entries")):
                if isinstance(entry, dict):
                    path = entry.get("path_str")
                    if path:
                        current_paths.add(path)

            # Fichiers nouveaux/inconnus
            new_paths = current_paths - previous_keep_paths

            if not new_paths:
                # ✅ TOUS connus → ignorer ce groupe
                continue
            else:
                # ❌ Il y a du nouveau → afficher et pré-marquer les anciens
                keeper_hints[group_id] = list(previous_keep_paths)
                filtered.append(group)
        else:
            # Groupe non vu avant → afficher normalement
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
        emit("Cache absent, reconstruction en cours", 0, "cache")
        rebuild_library_cache_full_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: emit(
                message=message, progress=progress, stage=stage
            )
        )
        library = load_library_cache(library_cache_file) or []

    emit("Analyse avancée des doublons en cours", 10, "dedup")

    try:
        groups, rejected_pairs = build_dedup_groups(library)
    except Exception as e:
        emit(f"Erreur dédup : {e}", 100, "error")
        raise

    duplicate_files = sum(max((len(g.get("duplicates", [])) for g in groups), default=0) for g in groups)

    # ✅ Appliquer les filtres de choix précédents
    filtered_groups, keeper_hints = filter_and_preselect_dedup_groups(groups)

    # Regrouper par album
    album_groups = group_dedup_groups_by_album(filtered_groups)

    report = {
        "generated_at": int(time.time()),
        "group_count": len(filtered_groups),      # Groupes affichés
        "total_group_count": len(groups),          # Tous les groupes trouvés
        "duplicate_file_count": sum(len(g.get("duplicates", [])) for g in filtered_groups),
        "album_groups": album_groups,
        "groups": filtered_groups,
        "keeper_hints": keeper_hints,              # ✅ NOUVEAU: Pour pré-cocher
        "rejected_pairs": rejected_pairs[:1000],
    }

    save_dedup_report(report)

    emit(
        message=f"Analyse terminée : {len(filtered_groups)} groupe(s) à vérifier, {len(groups) - len(filtered_groups)} groupe(s) déjà validé(s), {report['duplicate_file_count']} doublons candidats",
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

    # ✅ NOUVEAU: Sauvegarder les choix utilisateur pour les prochains scans
    existing_choices = load_dedup_choices() or {}
    groups_by_id = {g.get("group_id"): g for g in safe_list(report.get("groups"))}

    for decision in safe_list(decisions):
        group_id = decision.get("group_id")
        keep_paths = set(str(p) for p in safe_list(decision.get("keep_paths")))
        group = groups_by_id.get(group_id)
        if not group:
            continue

        # Créer une clé unique pour ce groupe de chansons
        group_key = dedup_group_key(group)

        # Sauvegarder/fusionner les choix
        if group_key not in existing_choices:
            existing_choices[group_key] = {
                "identity": group.get("identity", {}),
                "keep_paths": []
            }

        # Ajouter les nouveaux chemins (éviter les doublons)
        existing_paths = set(existing_choices[group_key].get("keep_paths", []))
        existing_paths.update(keep_paths)
        existing_choices[group_key]["keep_paths"] = list(existing_paths)

    # Sauvegarder le fichier JSON
    save_dedup_choices(existing_choices)

    return {"processed": len(results), "results": results}


AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wv", ".mp4"}


def env_list(name: str, default=None):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_host_to_navidrome_roots(name: str, default=None):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return list(default or [])

    mappings = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            continue
        host, navidrome = item.split(":", 1)
        host = host.strip()
        navidrome = navidrome.strip()
        if host and navidrome:
            mappings.append({"host": host, "navidrome": navidrome})
    return mappings


DEFAULT_CONFIG = {
    "scan_dirs": env_list("SCAN_DIRS", ["/music/deezer-dl", "/music/library"]),
    "playlists_base_dir": os.environ.get(
        "PLAYLISTS_BASE_DIR", "/music/playlists"
    ).strip()
    or "/music/playlists",
    "playlist_ids_file": str(PLAYLIST_IDS_FILE),
    "library_cache_file": str(LIBRARY_CACHE_FILE),
    "preview_state_file": str(PREVIEW_STATE_FILE),
    "host_to_navidrome_roots": env_host_to_navidrome_roots(
        "HOST_TO_NAVIDROME_ROOT",
        [
            {"host": "/music/deezer-dl", "navidrome": "/deezer-dl"},
            {"host": "/music/library", "navidrome": "/music"},
        ],
    ),
    "deezer_dl_base_url": os.environ.get(
        "DEEZER_DL_BASE_URL", "https://deezerdl.example.com"
    ).strip()
    or "https://deezerdl.example.com",
}

TASKS = {}


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)


def create_task():
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "queue": Queue(),
        "done": False,
        "error": None,
    }
    return task_id


def push_task_event(task_id, message=None, progress=None, stage=None, done=False, error=False):
    task = TASKS.get(task_id)
    if not task:
        return

    payload = {
        "type": "status",
        "message": message,
        "progress": progress,
        "stage": stage,
        "done": done,
        "error": error,
        "timestamp": int(time.time()),
    }
    task["queue"].put(payload)
    if done:
        task["done"] = True


def push_task_row_update(task_id, row):
    task = TASKS.get(task_id)
    if not task:
        return
    payload = {
        "type": "row_update",
        "row": row,
        "timestamp": int(time.time()),
    }
    task["queue"].put(payload)


def load_config():
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = DEFAULT_CONFIG.copy()
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    return merged


def save_config(cfg):
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_preview_state_path():
    cfg = load_config()
    path = cfg.get("preview_state_file") or str(PREVIEW_STATE_FILE)
    return Path(path)


def load_preview_state():
    ensure_dirs()
    path = get_preview_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_preview_state(state):
    ensure_dirs()
    path = get_preview_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def update_preview_state(playlist_id, payload):
    state = load_preview_state()
    state[str(playlist_id)] = payload
    save_preview_state(state)


def get_preview_state(playlist_id):
    state = load_preview_state()
    return state.get(str(playlist_id))


def delete_playlist_cache(playlist_id: str):
    cover_path = COVERS_DIR / f"{playlist_id}.jpg"
    try:
        if cover_path.exists():
            cover_path.unlink()
    except Exception:
        pass
    try:
        state = load_preview_state()
        if str(playlist_id) in state:
            state.pop(str(playlist_id), None)
        save_preview_state(state)
    except Exception:
        pass


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio() if a and b else 0.0


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    return re.sub(r"\s+", " ", name).strip()


def extract_playlist_id(text: str):
    text = (text or "").strip()
    if text.isdigit():
        return text
    m = re.search(r"/playlist/(\d+)", text)
    return m.group(1) if m else None


def safe_get_first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def read_tags(path: Path):
    artist = ""
    title = ""
    album = ""
    duration = None
    try:
        audio = MutagenFile(path)
        if audio is not None:
            if getattr(audio, "info", None) and getattr(audio.info, "length", None):
                duration = float(audio.info.length)
            tags = getattr(audio, "tags", {}) or {}
            if path.suffix.lower() == ".mp3":
                artist = str(safe_get_first(tags.get("TPE1", [""])))
                title = str(safe_get_first(tags.get("TIT2", [""])))
                album = str(safe_get_first(tags.get("TALB", [""])))
            else:
                artist = str(safe_get_first(tags.get("artist", [""])))
                title = str(safe_get_first(tags.get("title", [""])))
                album = str(safe_get_first(tags.get("album", [""])))
    except Exception:
        pass
    return {
        "artist": artist.strip(),
        "title": title.strip(),
        "album": album.strip(),
        "duration": duration,
    }


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


def get_file_signature(path: Path):
    st = path.stat()
    return st.st_mtime_ns, st.st_size


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


def scan_audio_files(scan_dirs):
    files = []
    for base in scan_dirs:
        if not base.exists():
            continue
        for root, _, filenames in os.walk(base):
            for filename in filenames:
                path = Path(root) / filename
                if path.suffix.lower() in AUDIO_EXTS:
                    files.append(path)
    return files


def save_library_cache(library, library_cache_file):
    payload = {
        "generated_at": int(time.time()),
        "count": len(library),
        "library": library,
    }
    library_cache_file.parent.mkdir(parents=True, exist_ok=True)
    library_cache_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_library_cache(library_cache_file):
    if not library_cache_file.exists():
        return []
    try:
        data = json.loads(library_cache_file.read_text(encoding="utf-8"))
        return data.get("library", [])
    except Exception:
        return []


def rebuild_library_cache_full():
    scan_dirs, _, library_cache_file, _ = get_paths_from_config()
    files = scan_audio_files(scan_dirs)
    library = []
    max_workers = min(16, (os.cpu_count() or 4) + 4)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(build_library_entry, path, scan_dirs) for path in files]
        for future in as_completed(futures):
            try:
                library.append(future.result())
            except Exception:
                pass

    library.sort(key=lambda x: x["path_str"])
    save_library_cache(library, library_cache_file)
    return {"count": len(library)}


def rebuild_library_cache_full_with_progress(progress_cb=None):
    def emit(message=None, progress=None, stage=None):
        if progress_cb:
            progress_cb(message=message, progress=progress, stage=stage)

    scan_dirs, _, library_cache_file, _ = get_paths_from_config()
    files = scan_audio_files(scan_dirs)
    total = len(files)

    emit(f"Scan de la bibliothèque : {total} fichiers détectés", stage="cache", progress=0)

    library = []
    max_workers = min(16, (os.cpu_count() or 4) + 4)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(build_library_entry, path, scan_dirs) for path in files]
        for future in as_completed(futures):
            try:
                library.append(future.result())
            except Exception:
                pass
            done += 1
            progress = round((done / total) * 100) if total else 100
            if done % 50 == 0 or done == total:
                emit(
                    f"Analyse bibliothèque : {done}/{total}",
                    stage="cache",
                    progress=progress,
                )

    library.sort(key=lambda x: x["path_str"])
    save_library_cache(library, library_cache_file)
    emit("Cache bibliothèque reconstruit", stage="cache", progress=100)
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

    rebuilt = []
    max_workers = min(16, (os.cpu_count() or 4) + 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(build_library_entry, path, scan_dirs) for path in changed]
        for future in as_completed(futures):
            try:
                rebuilt.append(future.result())
            except Exception:
                pass

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
    current_files = scan_audio_files(scan_dirs)
    current_paths = {str(p): p for p in current_files}

    reused = []
    changed = []

    emit("Scan des fichiers existants", stage="cache", progress=0)

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
    rebuilt = []

    emit(f"Analyse {total} fichiers à recréer", stage="cache", progress=0)

    if total:
        max_workers = min(16, (os.cpu_count() or 4) + 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(build_library_entry, path, scan_dirs) for path in changed]
            for done, future in enumerate(as_completed(futures), start=1):
                try:
                    rebuilt.append(future.result())
                except Exception:
                    pass
                emit(
                    f"Analyse fichiers : {done}/{total}",
                    stage="cache",
                    progress=round((done / total) * 100),
                )

    new_library = sorted(reused + rebuilt, key=lambda x: x["path_str"])
    save_library_cache(new_library, library_cache_file)
    emit("Cache incrémental reconstruit", stage="cache", progress=100)

    return {"count": len(new_library), "reused": len(reused), "rebuilt": len(rebuilt)}


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
        cleaned.append(
            {
                "id": pid,
                "title": str(item.get("title", "")).strip() or "Titre inconnu",
                "picture": str(item.get("picture", "")).strip(),
            }
        )
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
                    title = title or "Titre inconnu"
            playlists.append({"id": pid, "title": title, "picture": picture})
    elif isinstance(data.get("playlist_ids"), list):
        for raw in data["playlist_ids"]:
            pid = str(raw).strip()
            if not pid.isdigit():
                continue
            try:
                info = fetch_deezer_playlist_info(pid)
                playlists.append(info)
            except Exception:
                playlists.append(
                    {"id": pid, "title": "Titre inconnu", "picture": ""}
                )
                changed = True

    playlists = sorted(
        {p["id"]: p for p in playlists}.values(), key=lambda x: int(x["id"])
    )

    if changed:
        save_playlists(playlists)

    for p in playlists:
        p["cover_cached"] = cache_cover(p)

    return playlists


def get_paths_from_config():
    cfg = load_config()
    scan_dirs = [Path(p) for p in cfg.get("scan_dirs", []) if p]
    playlists_base_dir = Path(cfg.get("playlists_base_dir", "/music/playlists"))
    library_cache_file = Path(cfg.get("library_cache_file", str(LIBRARY_CACHE_FILE)))
    mappings = {
        Path(m["host"]): Path(m["navidrome"])
        for m in cfg.get("host_to_navidrome_roots", [])
        if m.get("host") and m.get("navidrome")
    }
    return scan_dirs, playlists_base_dir, library_cache_file, mappings


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

    return {
        "score": round(score, 4),
        "title_score": round(title_score, 4),
        "artist_score": round(artist_score, 4),
        "album_score": round(album_score, 4),
    }


def find_best_match(track, library):
    best = None
    best_data = None
    for entry in library:
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
    raise ValueError(f"Chemin non mappé pour Navidrome: {path}")


def relative_m3u_path(playlist_dir_host: Path, audio_file_host: Path, mappings) -> str:
    audio_file_nav = map_host_path_to_navidrome(audio_file_host, mappings)
    rel = os.path.relpath(str(audio_file_nav), start=str(playlist_dir_host)).replace(
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


def convert_playlist(playlist_id: str, progress_cb=None):
    def emit(message=None, progress=None, stage=None, row_update=None):
        if progress_cb:
            progress_cb(
                message=message,
                progress=progress,
                stage=stage,
                row_update=row_update,
            )

    _, playlists_base_dir, library_cache_file, mappings = get_paths_from_config()

    emit("Récupération des informations Deezer", stage="deezer")
    playlist_title, deezer_tracks = fetch_deezer_playlist_tracks(playlist_id)

    library = load_library_cache(library_cache_file)
    if not library:
        emit("Cache bibliothèque vide, rebuild complet en cours", stage="cache")
        rebuild_library_cache_full_with_progress(
            progress_cb=lambda message=None, progress=None, stage=None: emit(
                message=message, progress=progress, stage=stage
            )
        )
        library = load_library_cache(library_cache_file)

    emit("Matching des morceaux", stage="matching", progress=0)

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

    total = len(deezer_tracks)

    for idx, track in enumerate(deezer_tracks, start=1):
        emit(
            f"Matching {idx}/{total} : {track['artist']} - {track['title']}",
            stage="matching",
            progress=round((idx / total) * 100),
        )

        best = find_best_match(track, library)
        deezer_name = (
            f"{track['artist']} - {track['title']}" if track["artist"] else track["title"]
        )

        item = {
            "position": track["position"],
            "deezer_artist": track["artist"],
            "deezer_title": track["title"],
            "deezer_album": track["album"],
        }

        if best is None:
            report["unmatched_count"] += 1
            item["matched"] = False
            missing_lines.append(f"{track['artist']} - {track['title']} [{track['album']}]")
            preview_row = {
                "convert": "❌",
                "number": track["position"],
                "deezer_name": deezer_name,
                "source_name": "not found",
                "matched": False,
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
            source_name = (
                f"{source_artist} - {source_title}" if source_artist else source_title
            )

            preview_row = {
                "convert": "✅",
                "number": track["position"],
                "deezer_name": deezer_name,
                "source_name": source_name,
                "matched": True,
                "track_id": track.get("track_id"),
                "downloaded": False,
            }

        report["tracks"].append(item)
        preview_rows.append(preview_row)
        emit(row_update=preview_row)

    emit("Écriture des fichiers de sortie", stage="write", progress=100)

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


def clear_library_cache_file():
    _, _, library_cache_file, _ = get_paths_from_config()
    try:
        if library_cache_file.exists():
            library_cache_file.unlink()
    except Exception:
        pass


def clear_preview_state_file():
    try:
        path = get_preview_state_path()
        if path.exists():
            path.unlink()
    except Exception:
        pass


def clear_playlists_and_covers():
    try:
        if PLAYLIST_IDS_FILE.exists():
            PLAYLIST_IDS_FILE.unlink()
    except Exception:
        pass
    try:
        if COVERS_DIR.exists():
            for f in COVERS_DIR.glob("*.jpg"):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass
    clear_preview_state_file()


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

    type_map = {
        "track": "track",
        "album": "album",
        "artist": "artist",
    }
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
                    "title": item.get("title") or "Titre inconnu",
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
                    "subtitle": ((item.get("artist") or {}).get("name"))
                    or "Artiste inconnu",
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
                "title": t.get("title") or "Titre inconnu",
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


@app.route("/")
def home():
    playlists = load_playlists()
    return render_template("home.html", playlists=playlists)


@app.get("/search")
def search_route():
    q = (request.args.get("q") or "").strip()
    search_type = (request.args.get("type") or "track").strip().lower()
    if search_type not in {"track", "album", "artist"}:
        return jsonify({"ok": False, "error": "type invalide"}), 400
    if not q:
        return jsonify({"ok": True, "results": []})
    try:
        results = search_deezer(q, search_type)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/covers/<path:filename>")
def serve_cover(filename):
    return send_from_directory(COVERS_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/config", methods=["GET", "POST"])
def config_view():
    if request.method == "POST":
        scan_dirs = [
            x.strip()
            for x in request.form.get("scan_dirs", "").splitlines()
            if x.strip()
        ]
        playlists_base_dir = request.form.get("playlists_base_dir", "").strip()
        playlist_ids_file = request.form.get("playlist_ids_file", "").strip()
        library_cache_file = request.form.get("library_cache_file", "").strip()
        preview_state_file = request.form.get("preview_state_file", "").strip()
        deezer_dl_base_url = request.form.get("deezer_dl_base_url", "").strip().rstrip(
            "/"
        )

        mapping_hosts = request.form.getlist("mapping_host[]")
        mapping_navs = request.form.getlist("mapping_navidrome[]")

        mappings = []
        for h, n in zip(mapping_hosts, mapping_navs):
            h = h.strip()
            n = n.strip()
            if h and n:
                mappings.append({"host": h, "navidrome": n})

        cfg = {
            "scan_dirs": scan_dirs,
            "playlists_base_dir": playlists_base_dir,
            "playlist_ids_file": playlist_ids_file or str(PLAYLIST_IDS_FILE),
            "library_cache_file": library_cache_file or str(LIBRARY_CACHE_FILE),
            "preview_state_file": preview_state_file or str(PREVIEW_STATE_FILE),
            "host_to_navidrome_roots": mappings,
            "deezer_dl_base_url": deezer_dl_base_url or "https://deezerdl.example.com",
        }
        save_config(cfg)
        flash("Configuration sauvegardée")
        return redirect(url_for("config_view"))

    cfg = load_config()
    return render_template("config.html", config=cfg)


@app.post("/playlist/add")
def add_playlist():
    value = request.form.get("playlist_input", "")
    pid = extract_playlist_id(value)
    if not pid:
        flash("ID ou URL invalide")
        return redirect(url_for("home"))

    playlists = load_playlists()
    if any(p["id"] == pid for p in playlists):
        flash("Playlist déjà enregistrée")
        return redirect(url_for("home"))

    info = fetch_deezer_playlist_info(pid)
    playlists.append(info)
    save_playlists(playlists)
    cache_cover(info)
    flash("Playlist ajoutée")
    return redirect(url_for("home"))


@app.post("/playlist/<playlist_id>/delete")
def delete_playlist(playlist_id):
    playlists = [p for p in load_playlists() if p["id"] != playlist_id]
    save_playlists(playlists)
    delete_playlist_cache(playlist_id)
    flash("Playlist supprimée")
    return redirect(url_for("home"))


@app.post("/playlist/<playlist_id>/convert")
def convert_playlist_route(playlist_id):
    try:
        result = convert_playlist(playlist_id)
        flash(
            f"Conversion OK: {result['playlist_title']} ({result['matched']} matchés, {result['unmatched']} manquants)"
        )
    except Exception as e:
        flash(f"Erreur conversion: {e}")
    return redirect(url_for("home"))


@app.post("/playlist/<playlist_id>/convert/start")
def convert_playlist_start(playlist_id):
    task_id = create_task()

    def on_progress(message=None, progress=None, stage=None, row_update=None):
        if row_update is not None:
            push_task_row_update(task_id, row_update)
        if message is not None or progress is not None or stage is not None:
            push_task_event(
                task_id,
                message=message,
                progress=progress,
                stage=stage,
            )

    def runner():
        try:
            push_task_event(
                task_id,
                "Initialisation de la conversion",
                stage="init",
                progress=0,
            )
            result = convert_playlist(playlist_id, progress_cb=on_progress)
            push_task_event(
                task_id,
                f"Conversion terminée : {result['playlist_title']} ({result['matched']} matchés, {result['unmatched']} manquants)",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur conversion : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.get("/playlist/<playlist_id>/preview")
def playlist_preview_route(playlist_id):
    try:
        data = build_playlist_preview(playlist_id)
        return jsonify({"ok": True, "playlist": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/playlist/<playlist_id>/download-missing/start")
def download_missing_start(playlist_id: str):
    preview = get_preview_state(playlist_id)
    if not preview or not isinstance(preview.get("rows"), list):
        return jsonify(
            {"error": "Preview introuvable, lance d'abord une conversion"}
        ), 400

    missing_rows = [
        row
        for row in preview["rows"]
        if row.get("matched") is False
        and row.get("track_id")
        and not row.get("downloaded")
    ]
    if not missing_rows:
        return jsonify({"error": "Aucune musique manquante à télécharger"}), 400

    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url non configuré"}), 400

    task_id = create_task()

    def runner():
        total = len(missing_rows)
        pending_ids = {str(row["track_id"]).strip() for row in missing_rows if row.get("track_id") is not None}
        log_dl(f"missing track ids: {sorted(pending_ids)}")
        success_ids = set()
        failed_ids = set()

        try:
            push_task_event(
                task_id,
                "Début du téléchargement des musiques manquantes",
                stage="download_missing",
                progress=0,
            )

            for row in missing_rows:
                track_id = str(row["track_id"]).strip()
                log_dl(f"launch download track_id={track_id}")
                try:
                    resp = requests.post(
                        f"{base_url}/download",
                        json={
                            "type": "track",
                            "music_id": int(track_id),
                            "add_to_playlist": False,
                            "create_zip": False,
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    log_dl(
                        f"download request sent track_id={track_id} status={resp.status_code}"
                    )
                except Exception:
                    failed_ids.add(track_id)
                    pending_ids.discard(track_id)

            idle_loops = 0
            max_idle_loops = 120

            while pending_ids and idle_loops < max_idle_loops:
                time.sleep(3)
                try:
                    queue_resp = requests.get(f"{base_url}/queue", timeout=30)
                    queue_resp.raise_for_status()
                    queue_items = parse_queue_items(queue_resp.json())
                except Exception:
                    idle_loops += 1
                    push_task_event(
                        task_id,
                        f"Vérification de la queue… {len(success_ids)}/{total} téléchargées",
                        stage="download_missing",
                        progress=round(
                            ((len(success_ids) + len(failed_ids)) / total) * 100
                        ),
                    )
                    continue

                completed_now = set()
                failed_now = set()

                for item in queue_items:
                    tid = extract_track_id_from_queue_item(item)
                    state = extract_queue_state(item)
                    result = item.get("result")
                    log_dl(
                        f"queue item raw_track_id={tid} state={state} result={result} pending={sorted(pending_ids)}"
                    )

                    if not tid:
                        continue
                    tid = str(tid).strip()
                    if tid not in pending_ids:
                        continue

                    if state == "mission accomplished":
                        completed_now.add(tid)
                        log_dl(f"TRACK DONE tid={tid}")
                    elif state == "failed":
                        failed_now.add(tid)

                if completed_now:
                    success_ids.update(completed_now)
                    pending_ids.difference_update(completed_now)
                    changed_rows = mark_preview_rows_downloaded(
                        playlist_id, completed_now
                    )
                    for row in changed_rows:
                        push_task_row_update(task_id, row)

                    push_task_event(
                        task_id,
                        f"Music missing downloaded - {len(success_ids)}/{total}",
                        stage="download_missing",
                        progress=round(
                            ((len(success_ids) + len(failed_ids)) / total) * 100
                        ),
                    )

                if failed_now:
                    failed_ids.update(failed_now)
                    pending_ids.difference_update(failed_now)
                    push_task_event(
                        task_id,
                        f"Téléchargements en échec : {len(failed_ids)}",
                        stage="download_missing",
                        progress=round(
                            ((len(success_ids) + len(failed_ids)) / total) * 100
                        ),
                    )

                if not completed_now and not failed_now:
                    idle_loops += 1
                else:
                    idle_loops = 0

            if pending_ids:
                failed_ids.update(pending_ids)
                pending_ids.clear()

            push_task_event(
                task_id,
                f"Téléchargement terminé : {len(success_ids)} succès, {len(failed_ids)} échecs",
                stage="done",
                progress=100,
                done=True,
            )

        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur download missing : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id, "total": len(missing_rows)})


@app.post("/cache/rebuild")
def cache_rebuild_route():
    try:
        result = rebuild_library_cache_full()
        flash(f"Cache complet reconstruit: {result['count']} entrées")
    except Exception as e:
        flash(f"Erreur rebuild cache: {e}")
    return redirect(url_for("config_view"))


@app.post("/cache/full/start")
def cache_full_start():
    task_id = create_task()

    def runner():
        try:
            push_task_event(
                task_id,
                "Rebuild complet du cache en cours",
                stage="cache",
                progress=0,
            )
            result = rebuild_library_cache_full_with_progress(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id,
                    message=message,
                    progress=progress,
                    stage=stage,
                )
            )
            push_task_event(
                task_id,
                f"Rebuild complet terminé : {result['count']} entrées",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur rebuild complet : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.post("/cache/incremental/start")
def cache_incremental_start():
    task_id = create_task()

    def runner():
        try:
            push_task_event(
                task_id,
                "Refresh incrémental du cache en cours",
                stage="cache",
                progress=0,
            )
            result = refresh_library_cache_incremental_with_progress(
                progress_cb=lambda message=None, progress=None, stage=None: push_task_event(
                    task_id,
                    message=message,
                    progress=progress,
                    stage=stage,
                )
            )
            push_task_event(
                task_id,
                f"Refresh incrémental terminé : {result['count']} entrées, {result['rebuilt']} recalculées",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur refresh incrémental : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.post("/cache/refresh")
def cache_refresh_route():
    try:
        result = refresh_library_cache_incremental()
        flash(
            f"Cache incrémental OK: {result['count']} entrées, {result['rebuilt']} recalculées"
        )
    except Exception as e:
        flash(f"Erreur refresh cache: {e}")
    return redirect(url_for("config_view"))


@app.post("/dedup/start")
def dedup_start():
    task_id = create_task()

    def on_progress(message=None, progress=None, stage=None, payload=None):
        push_task_event(task_id, message=message, progress=progress, stage=stage)
        if payload is not None:
            task = TASKS.get(task_id)
            if task:
                task["queue"].put(
                    {
                        "type": "dedup_result",
                        "payload": payload,
                        "timestamp": int(time.time()),
                    }
                )

    def runner():
        try:
            push_task_event(
                task_id,
                "Initialisation de l'analyse de doublons",
                stage="init",
                progress=0,
            )
            report = run_dedup_analysis(progress_cb=on_progress)
            push_task_event(
                task_id,
                f"Dédup terminée : {report['group_count']} groupes",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur dédup : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.get("/dedup/report")
def dedup_report_route():
    report = load_dedup_report()
    if not report:
        return jsonify({"ok": False, "error": "Aucun rapport de déduplication"}), 404
    return jsonify({"ok": True, "report": report})


@app.post("/dedup/apply")
def dedup_apply_route():
    payload = request.get_json(silent=True) or {}
    decisions = payload.get("decisions", [])
    mode = payload.get("mode", "quarantine")
    if not decisions:
        return jsonify({"ok": False, "error": "Aucune décision fournie"}), 400
    result = apply_dedup_decisions(decisions, mode=mode)
    return jsonify({"ok": True, **result})


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/version")
def version_route():
    return jsonify({"version": get_app_version()})


@app.route("/api/latest-version")
def latest_version_route():
    result = get_latest_available_version()
    return jsonify({
        "current_version": get_app_version(),
        "latest_version": result["version"],
        "url": result["url"],
        "source": result["source"],
        "update_available": result["version"] is not None,
    })


@app.route("/tasks/<task_id>/stream")
def task_stream(task_id):
    def generate():
        task = TASKS.get(task_id)
        if not task:
            yield 'data: {"type":"status","message":"Tâche introuvable","done":true,"error":true}\n\n'
            return
        while True:
            try:
                event = task["queue"].get(timeout=15)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done"):
                    break
            except Empty:
                if task.get("done"):
                    break
                yield ": keepalive\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/deezer-dl/track/<track_id>", methods=["POST"])
def deezer_dl_track(track_id):
    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url non configuré"}), 400

    task_id = create_task()

    def run():
        try:
            push_task_event(
                task_id,
                message=f"Envoi de la requête DL pour track {track_id}…",
                stage="dl",
                progress=0,
            )
            payload = {
                "type": "track",
                "music_id": track_id,
                "add_to_playlist": False,
                "create_zip": False,
            }
            resp = requests.post(f"{base_url}/download", json=payload, timeout=60)
            if resp.status_code != 200:
                push_task_event(
                    task_id,
                    message=f"Erreur {resp.status_code} : {resp.text[:200]}",
                    stage="dl",
                    done=True,
                    error=True,
                )
                return
            data = resp.json()
            push_task_event(
                task_id,
                message=f"Téléchargement lancé : {data.get('file') or data.get('message') or 'OK'}",
                stage="dl",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                message=f"Exception : {e}",
                stage="dl",
                done=True,
                error=True,
            )

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.get("/deezer-dl/queue")
def deezer_dl_queue():
    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url non configuré"}), 400
    try:
        resp = requests.get(f"{base_url}/queue", timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return jsonify({"error": f"Erreur appel /queue : {e}"}), 502
    return jsonify(resp.json())


@app.post("/deezer-dl/download/start")
def deezer_dl_download_start():
    data = request.get_json(silent=True) or {}
    download_type = str(data.get("type") or "").strip().lower()
    music_id = str(data.get("music_id") or "").strip()
    if download_type not in {"track", "album", "artist"}:
        return jsonify({"error": "type invalide"}), 400
    if not music_id.isdigit():
        return jsonify({"error": "music_id invalide"}), 400

    cfg = load_config()
    base_url = (cfg.get("deezer_dl_base_url") or "").rstrip("/")
    if not base_url:
        return jsonify({"error": "deezer_dl_base_url non configuré"}), 400

    task_id = create_task()

    def runner():
        try:
            push_task_event(
                task_id,
                f"Lancement téléchargement {download_type} {music_id}",
                stage="download",
                progress=0,
            )
            payload = {
                "type": download_type,
                "music_id": int(music_id),
                "add_to_playlist": False,
                "create_zip": False,
            }
            resp = requests.post(f"{base_url}/download", json=payload, timeout=60)
            resp.raise_for_status()
            push_task_event(
                task_id,
                f"Téléchargement lancé pour {download_type} {music_id}",
                stage="done",
                progress=100,
                done=True,
            )
        except Exception as e:
            push_task_event(
                task_id,
                f"Erreur lancement téléchargement : {e}",
                stage="error",
                done=True,
                error=True,
            )

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.get("/search/album/<album_id>")
def search_album_detail_route(album_id):
    try:
        return jsonify({"ok": True, "album": fetch_deezer_album_details(album_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/search/artist/<artist_id>")
def search_artist_detail_route(artist_id):
    try:
        return jsonify({"ok": True, "artist": fetch_deezer_artist_details(artist_id)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/admin/clear/library-cache")
def clear_library_cache_route():
    clear_library_cache_file()
    flash("music_library_cache vidé")
    return redirect(url_for("config_view"))


@app.post("/admin/clear/preview-state")
def clear_preview_state_route():
    clear_preview_state_file()
    flash("playlist_preview_state vidé")
    return redirect(url_for("config_view"))


@app.post("/admin/clear/playlists")
def clear_playlists_route():
    clear_playlists_and_covers()
    flash("Playlists, covers et playlist_preview_state vidés")
    return redirect(url_for("config_view"))


@app.post("/admin/clear/all")
def clear_all_route():
    clear_playlists_and_covers()
    clear_library_cache_file()
    flash("Tout vidé : playlists, covers, playlist_preview_state et music_library_cache")
    return redirect(url_for("config_view"))


def log_dl(msg):
    print(f"[download-missing] {msg}", flush=True)


if __name__ == "__main__":
    ensure_dirs()
    app.run(host="0.0.0.0", port=8080, debug=False)
