"""One-time changes to the data of an existing install, run at start-up.

Each step is safe to run again and never stops the app: a failure is logged
and the next start tries again."""
import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)
BACKUP_FOLDER = "pre-1.16.0"


def backup(path: Path) -> None:
    """A copy in DATA_DIR/backups/pre-1.16.0, made once, before the first change."""
    from core import config

    target = Path(config.DATA_DIR) / "backups" / BACKUP_FOLDER / path.name
    if path.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def playlist_accounts() -> int:
    """Playlists saved before 1.16 belong to the account made from the install,
    written down so it no longer depends on which account is the default."""
    from core import nd_accounts
    from core.config import PLAYLIST_IDS_FILE

    try:
        data = json.loads(PLAYLIST_IDS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    entries = data.get("playlists") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return 0
    missing = [e for e in entries if isinstance(e, dict) and not e.get("accounts")]
    owner = nd_accounts.owner_fallback()
    if not missing or not owner:
        return 0
    backup(PLAYLIST_IDS_FILE)
    for entry in missing:
        entry["accounts"] = [owner]
    partial = PLAYLIST_IDS_FILE.with_name(f".{PLAYLIST_IDS_FILE.name}.part")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(partial, PLAYLIST_IDS_FILE)
    return len(missing)


def run() -> None:
    from core import config, nd_accounts

    try:
        changed = config.encrypt_stored_secrets()
        if changed:
            logger.info("Encrypted %s secrets in secrets.json", changed)
    except Exception as e:
        logger.error("Could not encrypt secrets.json: %s", e)
    try:
        made = nd_accounts.ensure_initial()
        if made:
            logger.info("Navidrome account nd1 created from this install (user: %s)", made["username"] or "unknown")
    except Exception as e:
        logger.error("Could not set up the first Navidrome account: %s", e)
    try:
        given = playlist_accounts()
        if given:
            logger.info("%s playlists now belong to the first Navidrome account", given)
    except Exception as e:
        logger.error("Could not give the playlists to the first Navidrome account: %s", e)
