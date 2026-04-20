import json
import os
import time
import uuid
from pathlib import Path
from queue import Queue

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
COVERS_DIR = DATA_DIR / "covers"
CONFIG_FILE = DATA_DIR / "config.json"
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
    "deezer_dl_base_url": os.environ.get("DEEZER_DL_BASE_URL", "https://deezerdl.example.com").strip()
    or "https://deezerdl.example.com",
    "library_workers_per_dir": int(os.environ.get("LIBRARY_WORKERS_PER_DIR", "2") or "2"),
    "match_workers": int(os.environ.get("MATCH_WORKERS", "4") or "4"),
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
