import json
import os
import threading
import time
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
COVERS_DIR = DATA_DIR / "covers"
CONFIG_FILE = DATA_DIR / "config.json"
# Credentials live apart from config.json, which is meant to be shareable (see .gitignore).
SECRETS_FILE = DATA_DIR / "secrets.json"
PLAYLIST_IDS_FILE = DATA_DIR / "deezer_playlist_ids.json"
LIBRARY_CACHE_FILE = DATA_DIR / "music_library_cache.json"
PREVIEW_STATE_FILE = DATA_DIR / "playlist_preview_state.json"
DEDUP_REPORT_FILE = DATA_DIR / "dedup_report.json"
DEDUP_QUARANTINE_DIR = DATA_DIR / "dedup_quarantine"
DEDUP_CHOICES_FILE = DATA_DIR / "dedup_choices.json"


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
        if not item or ":" not in item:
            continue
        host, navidrome = item.split(":", 1)
        host = host.strip()
        navidrome = navidrome.strip()
        if host and navidrome:
            mappings.append({"host": host, "navidrome": navidrome})
    return mappings


# The release notes shown once in the Help window. A new install starts with
# them read; an install upgraded from before the built-in downloader still has
# the old downloader address in its config.json, which is how it is spotted.
WHATS_NEW_ID = "1.11"
LEGACY_DOWNLOADER_KEY = "deezer_dl_base_url"

DEFAULT_CONFIG = {
    "scan_dirs": env_list("SCAN_DIRS", ["/music/deezer-dl", "/music/library"]),
    "playlists_base_dir": os.environ.get("PLAYLISTS_BASE_DIR", "/music/playlists").strip()
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
    # Empty: the deezer-dl folder of the music folders (see deezer_dl.download_dir).
    "deezer_dl_dir": os.environ.get("DEEZER_DL_DIR", "").strip(),
    "library_workers_per_dir": int(os.environ.get("LIBRARY_WORKERS_PER_DIR", "2") or "2"),
    "match_workers": int(os.environ.get("MATCH_WORKERS", "4") or "4"),
    # Threads downloading from Deezer at the same time.
    "download_workers": int(os.environ.get("DOWNLOAD_WORKERS", "4") or "4"),
    # Hours between automatic refreshes of the release feed; 0 = manual only.
    "release_refresh_hours": 24,
    "notes_seen": WHATS_NEW_ID,
}

# Background tasks. Each keeps the full list of its events so any number of
# pages can follow it, including pages opened after it started.
TASKS = {}
_tasks_lock = threading.Lock()
TASK_RETENTION_SECONDS = 30 * 60


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)


def _prune_tasks():
    limit = time.time() - TASK_RETENTION_SECONDS
    with _tasks_lock:
        for task_id in [k for k, t in TASKS.items() if t["done"] and (t["finished_at"] or 0) < limit]:
            TASKS.pop(task_id, None)


def create_task(title="Task", kind="task", playlist_id=None, visible=True):
    """`visible` tasks are listed in Activity; small ones (single downloads) are not."""
    _prune_tasks()
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        TASKS[task_id] = {
            "id": task_id,
            "title": title,
            "kind": kind,
            "playlist_id": str(playlist_id) if playlist_id else None,
            "visible": visible,
            "created_at": time.time(),
            "finished_at": None,
            "done": False,
            "error": False,
            "stage": None,
            "message": None,
            "progress": None,
            "events": [],
            "cond": threading.Condition(),
        }
    return task_id


def push_task_payload(task_id, payload):
    task = TASKS.get(task_id)
    if not task:
        return
    with task["cond"]:
        if payload.get("type") == "status":
            for key in ("message", "stage", "progress"):
                if payload.get(key) is not None:
                    task[key] = payload[key]
            if payload.get("done"):
                task["done"] = True
                task["error"] = bool(payload.get("error"))
                task["finished_at"] = time.time()
        task["events"].append(payload)
        task["cond"].notify_all()


def push_task_event(task_id, message=None, progress=None, stage=None, done=False, error=False):
    push_task_payload(task_id, {
        "type": "status",
        "message": message,
        "progress": progress,
        "stage": stage,
        "done": done,
        "error": error,
        "timestamp": int(time.time()),
    })


def push_task_row_update(task_id, row):
    push_task_payload(task_id, {"type": "row_update", "row": row, "timestamp": int(time.time())})


def task_summary(task):
    return {k: task[k] for k in (
        "id", "title", "kind", "playlist_id", "created_at", "finished_at",
        "done", "error", "stage", "message", "progress",
    )}


def list_tasks():
    _prune_tasks()
    with _tasks_lock:
        tasks = [t for t in TASKS.values() if t["visible"]]
    return [task_summary(t) for t in sorted(tasks, key=lambda t: t["created_at"], reverse=True)]


def follow_task(task_id, start=0, keepalive=15):
    """Yields (index, event) for every event of a task from `start` on, then new
    ones as they come; yields (None, None) when nothing happened for
    `keepalive` seconds. The index lets a reconnecting client resume."""
    task = TASKS.get(task_id)
    if not task:
        return
    sent = max(0, start)
    while True:
        with task["cond"]:
            if sent >= len(task["events"]) and not task["done"]:
                task["cond"].wait(timeout=keepalive)
            pending = task["events"][sent:]
            finished = task["done"]
        if not pending:
            if finished:
                return
            yield None, None
            continue
        for offset, event in enumerate(pending):
            yield sent + offset, event
        sent += len(pending)
        if finished and sent >= len(task["events"]):
            return


def load_secret(name):
    """A credential from the environment (upper-case, DEEZER_ARL for "deezer_arl") or secrets.json."""
    env = os.environ.get(name.upper())
    if env:
        return env.strip()
    try:
        return (json.loads(SECRETS_FILE.read_text(encoding="utf-8")).get(name) or "").strip()
    except Exception:
        return ""


def secret_from_env(name):
    return bool(os.environ.get(name.upper()))


def save_secret(name, value):
    ensure_dirs()
    try:
        secrets = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        secrets = {}
    if value:
        secrets[name] = value
    else:
        secrets.pop(name, None)
    SECRETS_FILE.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
    try:
        SECRETS_FILE.chmod(0o600)
    except OSError:
        pass


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


def _raw_config():
    """config.json as saved, without the defaults filled in."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def whats_new_state():
    """Whether the Help window opens on its own, and if the install still used
    the separate downloader before this version."""
    raw = _raw_config()
    legacy = LEGACY_DOWNLOADER_KEY in raw
    return {
        "id": WHATS_NEW_ID,
        "legacy": legacy,
        "show": legacy or raw.get("notes_seen", WHATS_NEW_ID) != WHATS_NEW_ID,
    }


def mark_whats_new_seen():
    cfg = load_config()
    cfg.pop(LEGACY_DOWNLOADER_KEY, None)
    cfg["notes_seen"] = WHATS_NEW_ID
    save_config(cfg)


def kept_config_keys():
    """Keys the settings form does not edit but must not lose on save."""
    raw = _raw_config()
    return {key: raw[key] for key in ("notes_seen", LEGACY_DOWNLOADER_KEY) if key in raw}


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


# Scans, manual matches and download marks all rewrite the same file.
_preview_lock = threading.RLock()


def update_preview_state(playlist_id, payload):
    with _preview_lock:
        state = load_preview_state()
        state[str(playlist_id)] = payload
        save_preview_state(state)


def modify_preview_state(playlist_id, change):
    """Read-modify-write of one playlist's state under a lock; `change(old) -> new`."""
    with _preview_lock:
        state = load_preview_state()
        new = change(state.get(str(playlist_id)))
        state[str(playlist_id)] = new
        save_preview_state(state)
        return new


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


def clear_dedup_report_file():
    try:
        if DEDUP_REPORT_FILE.exists():
            DEDUP_REPORT_FILE.unlink()
    except Exception:
        pass


def clear_dedup_choices_file():
    try:
        if DEDUP_CHOICES_FILE.exists():
            DEDUP_CHOICES_FILE.unlink()
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
