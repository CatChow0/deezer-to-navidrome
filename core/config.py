import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path

from core import files
from core.patch_notes import RELEASES

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
COVERS_DIR = DATA_DIR / "covers"
CONFIG_FILE = DATA_DIR / "config.json"
# Credentials live apart from config.json, which is meant to be shareable (see .gitignore).
SECRETS_FILE = DATA_DIR / "secrets.json"
PLAYLIST_IDS_FILE = DATA_DIR / "deezer_playlist_ids.json"
LIBRARY_CACHE_FILE = DATA_DIR / "music_library_cache.json"
PREVIEW_STATE_FILE = DATA_DIR / "playlist_preview_state.json"
# Playlists imported from other platforms: their source tracks and the Deezer
# track picked for each one. Kept apart from the preview state, which every
# scan rewrites, because the picks are slow to rebuild.
CROSSPLATFORM_FILE = DATA_DIR / "crossplatform.json"
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


# The newest notes behind the New button. A new install starts with them read;
# any older install gets a dot on the button until it is opened (it has another
# notes_seen, or none before 1.11). An install upgraded from before the built-in
# downloader still has the old downloader address in its config.json: it gets
# the dot too, since the 1.10.0 note explains how to drop the old container.
WHATS_NEW_ID = RELEASES[0]["version"]
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
    "metadata_workers": int(os.environ.get("METADATA_WORKERS", "4") or "4"),
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


class TaskCancelled(Exception):
    """Raised by a task's next progress report once someone asked it to stop."""


def create_task(title="Task", kind="task", playlist_id=None, visible=True, cancellable=False):
    """`visible` tasks are listed in Activity; small ones (single downloads) are not.
    `cancellable` is only for tasks known to stop cleanly at a progress report."""
    _prune_tasks()
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        TASKS[task_id] = {
            "id": task_id,
            "title": title,
            "kind": kind,
            "playlist_id": str(playlist_id) if playlist_id else None,
            "visible": visible,
            "cancellable": cancellable,
            "cancel_requested": False,
            "cancelled": False,
            "created_at": time.time(),
            "updated_at": time.time(),
            "finished_at": None,
            "done": False,
            "error": False,
            "stage": None,
            "message": None,
            "progress": None,
            "events": [],
            "cond": threading.Condition(),
        }
    if cancellable:
        # The page learns from the first event that it can offer Cancel: it must not
        # have to wait for the first progress report, which can take a while.
        push_task_payload(task_id, {"type": "status", "message": "Starting", "stage": "starting", "progress": None,
                                    "done": False, "error": False, "timestamp": int(time.time())})
    return task_id


def push_task_payload(task_id, payload):
    task = TASKS.get(task_id)
    if not task:
        return
    with task["cond"]:
        if payload.get("type") == "status" and payload.get("done") and payload.get("error") and task["cancel_requested"]:
            # The task stopped because it was asked to: that is not a failure.
            payload = {**payload, "error": False, "cancelled": True, "message": "Cancelled", "stage": "cancelled"}
        if payload.get("cancelled"):
            task["cancelled"] = True
        if payload.get("type") == "status":
            for key in ("message", "stage", "progress"):
                if payload.get(key) is not None:
                    task[key] = payload[key]
            if payload.get("done"):
                task["done"] = True
                task["error"] = bool(payload.get("error"))
                task["finished_at"] = time.time()
        task["events"].append(payload)
        task["updated_at"] = time.time()
        task["cond"].notify_all()


def cancel_requested(task_id) -> bool:
    task = TASKS.get(task_id)
    return bool(task and task["cancel_requested"])


def request_cancel(task_id) -> bool:
    """Asks a task to stop. False when it cannot: unknown, finished, or not stoppable."""
    task = TASKS.get(task_id)
    if not task or task["done"] or not task["cancellable"]:
        return False
    task["cancel_requested"] = True
    push_task_payload(task_id, {
        "type": "status", "message": "Stopping", "stage": "stopping", "progress": None,
        "done": False, "error": False, "timestamp": int(time.time()),
    })
    return True


def finish_cancelled(task_id, message="Cancelled") -> None:
    push_task_payload(task_id, {
        "type": "status", "message": message, "stage": "cancelled", "progress": None,
        "done": True, "error": False, "cancelled": True, "timestamp": int(time.time()),
    })


def push_task_event(task_id, message=None, progress=None, stage=None, done=False, error=False, check_cancel=True):
    """`check_cancel=False` for a report made where stopping is handled another way."""
    if check_cancel and not done and cancel_requested(task_id):
        raise TaskCancelled()
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
    return {k: task.get(k) for k in (
        "id", "title", "kind", "playlist_id", "created_at", "updated_at", "finished_at",
        "done", "error", "stage", "message", "progress", "cancellable", "cancel_requested", "cancelled",
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


_secrets_lock = threading.RLock()


def _read_secrets() -> dict:
    data = files.read_json(SECRETS_FILE, {})
    return data if isinstance(data, dict) else {}


def _write_secrets(secrets: dict) -> None:
    files.write_json(SECRETS_FILE, secrets, private=True)


# The secrets an environment variable may set (upper-case: DEEZER_ARL for
# "deezer_arl"). Only these: APP_PASSWORD_HASH or FLASK_SECRET_KEY in the
# environment must not silently replace what the app stored, and APP_USERNAME
# alone (without APP_PASSWORD) must not rename the account made at setup.
_ENV_SECRETS = re.compile(r"^(deezer_arl|deezer_arl_premium|api_token|scrobble_token(_nd[1-9][0-9]*)?)$")


def _env_secret(name) -> str:
    return os.environ.get(name.upper(), "").strip() if _ENV_SECRETS.match(name) else ""


def load_secret(name):
    """A credential from the environment (for the names in _ENV_SECRETS) or
    secrets.json, where it is kept encrypted (core/crypto.py)."""
    from core import crypto

    env = _env_secret(name)
    if env:
        return env
    with _secrets_lock:
        value = str(_read_secrets().get(name) or "").strip()
    try:
        return crypto.decrypt(value).strip()
    except crypto.DecryptError:
        logger.error("The secret %s was encrypted with another key: enter it again", name)
        return ""


def secret_from_env(name):
    return bool(_env_secret(name))


def save_secret(name, value):
    from core import crypto

    with _secrets_lock:
        secrets = _read_secrets()
        if value:
            secrets[name] = crypto.encrypt(str(value))
        else:
            secrets.pop(name, None)
        _write_secrets(secrets)


def encrypt_stored_secrets() -> int:
    """Start-up: values written in clear by older versions, or with a key
    replaced since (D2N_ENCRYPTION_KEY set later), are encrypted with the key in
    use. A value no key can read is left as it is. Returns how many changed."""
    from core import crypto

    with _secrets_lock:
        secrets = _read_secrets()
        changed = 0
        for name, value in list(secrets.items()):
            if not isinstance(value, str) or not crypto.needs_rewrap(value):
                continue
            try:
                plain = crypto.decrypt(value)
            except crypto.DecryptError:
                logger.error("The secret %s was encrypted with another key: enter it again", name)
                continue
            secrets[name] = crypto.encrypt(plain)
            changed += 1
        if changed:
            _write_secrets(secrets)
    return changed


def load_config():
    ensure_dirs()
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    data = files.read_json(CONFIG_FILE, {})
    merged = DEFAULT_CONFIG.copy()
    merged.update(data if isinstance(data, dict) else {})
    return merged


def save_config(cfg):
    files.write_json(CONFIG_FILE, cfg)


_warned_paths = set()


def data_file(value, default: Path) -> Path:
    """A file chosen in the settings, kept inside DATA_DIR: these files are
    rewritten and deleted by the app, so a path elsewhere could make it delete
    or overwrite any file (a settings form posted from another site, say)."""
    if not value:
        return default
    path = Path(value)
    try:
        path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        # Once per path: the settings are read many times a minute.
        if path != default and str(path) not in _warned_paths:
            _warned_paths.add(str(path))
            logger.warning("%s is outside DATA_DIR: %s is used instead", value, default)
        return default
    return path


def _raw_config():
    """config.json as saved, without the defaults filled in."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def whats_new_state():
    """Whether the New button shows its dot, and if the install still used the
    separate downloader."""
    raw = _raw_config()
    legacy = LEGACY_DOWNLOADER_KEY in raw
    return {
        "id": WHATS_NEW_ID,
        "legacy": legacy,
        "show": legacy or raw.get("notes_seen") != WHATS_NEW_ID,
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
    return data_file(cfg.get("preview_state_file"), PREVIEW_STATE_FILE)


def load_preview_state():
    ensure_dirs()
    path = get_preview_state_path()
    data = files.read_json(path, {})
    return data if isinstance(data, dict) else {}


def save_preview_state(state):
    files.write_json(get_preview_state_path(), state)


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


_crossplatform_lock = threading.RLock()


def _load_crossplatform():
    data = files.read_json(CROSSPLATFORM_FILE, {})
    return data if isinstance(data, dict) else {}


def get_crossplatform_state(playlist_id):
    return _load_crossplatform().get(str(playlist_id))


def modify_crossplatform_state(playlist_id, change):
    """Read-modify-write of one imported playlist under a lock; `change(old) -> new`.
    A new value of None removes the playlist."""
    with _crossplatform_lock:
        ensure_dirs()
        state = _load_crossplatform()
        new = change(state.get(str(playlist_id)))
        if new is None:
            state.pop(str(playlist_id), None)
        else:
            state[str(playlist_id)] = new
        files.write_json(CROSSPLATFORM_FILE, state)
        return new


def _quiet_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Could not delete %s: %s", path, e)


def delete_playlist_cache(playlist_id: str):
    _quiet_unlink(COVERS_DIR / f"{playlist_id}.jpg")
    # Under the lock: a scan of another playlist may be saving the same file.
    with _preview_lock:
        state = load_preview_state()
        if state.pop(str(playlist_id), None) is not None:
            save_preview_state(state)
    if get_crossplatform_state(playlist_id) is not None:
        modify_crossplatform_state(playlist_id, lambda old: None)


def get_paths_from_config():
    cfg = load_config()
    scan_dirs = [Path(p) for p in cfg.get("scan_dirs", []) if p]
    playlists_base_dir = Path(cfg.get("playlists_base_dir", "/music/playlists"))
    library_cache_file = data_file(cfg.get("library_cache_file"), LIBRARY_CACHE_FILE)
    mappings = {
        Path(m["host"]): Path(m["navidrome"])
        for m in cfg.get("host_to_navidrome_roots", [])
        if m.get("host") and m.get("navidrome")
    }
    return scan_dirs, playlists_base_dir, library_cache_file, mappings


def clear_library_cache_file():
    _quiet_unlink(get_paths_from_config()[2])


def clear_preview_state_file():
    _quiet_unlink(get_preview_state_path())


def clear_dedup_report_file():
    _quiet_unlink(DEDUP_REPORT_FILE)


def clear_dedup_choices_file():
    _quiet_unlink(DEDUP_CHOICES_FILE)


def clear_playlists_and_covers():
    _quiet_unlink(PLAYLIST_IDS_FILE)
    for cover in COVERS_DIR.glob("*.jpg"):
        _quiet_unlink(cover)
    clear_preview_state_file()
    _quiet_unlink(CROSSPLATFORM_FILE)
