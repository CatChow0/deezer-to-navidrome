"""One-time changes to the data of an existing install, run at start-up.

Each step is safe to run again and never stops the app: a failure is logged
and the next start tries again."""
import json
import logging
import os
import shutil
from pathlib import Path

from core import files

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
    files.write_json(PLAYLIST_IDS_FILE, data)
    return len(missing)


def deezer_accounts_from_secrets() -> int:
    """The Deezer account of older versions (deezer_arl), and its premium one used
    for the downloads (deezer_arl_premium), become Deezer accounts. They then
    leave secrets.json, after a backup. The environment variables keep working:
    such an account reads its ARL there."""
    from core import config, deezer_accounts

    stored = config._read_secrets()
    fresh = not deezer_accounts.exists()
    main = config.load_secret("deezer_arl") if fresh and "deezer_arl" in stored else ""
    download = config.load_secret("deezer_arl_premium") if fresh and "deezer_arl_premium" in stored else ""
    if fresh and (main or download):
        backup(config.SECRETS_FILE)
    if os.environ.get(deezer_accounts.ENV_MAIN, "").strip():
        main = ""  # The environment variable wins, as it did.
    if os.environ.get(deezer_accounts.ENV_DOWNLOAD, "").strip():
        download = ""
    made = deezer_accounts.ensure_initial(stored_main=main, stored_download=download)
    if fresh:
        for name in ("deezer_arl", "deezer_arl_premium"):
            if name in stored:
                config.save_secret(name, "")
    return made


def playlist_covers() -> int:
    """1.21: Deezer playlists added through the account before then may show
    Deezer's grey placeholder (an album's cover asked as a playlist's). Their
    picture is forgotten once, and load_playlists() asks Deezer for it again."""
    from core.config import COVERS_DIR, DATA_DIR
    from core.deezer import modify_playlists

    done = Path(DATA_DIR) / ".playlist-covers-1.21"
    if done.exists():
        return 0
    fixed = []

    def change(entries):
        for entry in entries:
            pid = str(entry.get("id") or "")
            if pid.isdigit() and "/images/playlist/" in str(entry.get("picture") or ""):
                entry["picture"] = ""
                (COVERS_DIR / f"{pid}.jpg").unlink(missing_ok=True)
                fixed.append(pid)
        return entries

    modify_playlists(change)
    done.write_text("Deezer playlist covers asked again once, in 1.21.", encoding="utf-8")
    return len(fixed)


def app_accounts() -> bool:
    """1.20: the account of older versions becomes the Super-Admin, and owns
    every Navidrome and Deezer account, the download account and the devices."""
    from core import deezer_accounts, devices, nd_accounts, users

    made = users.ensure_initial()
    owner = users.superadmin()
    if owner is None:
        return False
    nd_accounts.set_owner([a["id"] for a in nd_accounts.list_accounts() if not a.get("owner")], owner["id"])
    deezer_accounts.set_owner([a["id"] for a in deezer_accounts.list_accounts() if not a.get("owner")], owner["id"])
    devices.claim_unowned(owner["id"])
    if made and deezer_accounts.download_id():
        users.set_field(owner["id"], "download_deezer", deezer_accounts.download_id())
    return made


def run() -> None:
    from core import config, library, nd_accounts

    try:
        changed = config.encrypt_stored_secrets()
        if changed:
            logger.info("Encrypted %s secrets in secrets.json", changed)
    except Exception as e:
        logger.error("Could not encrypt secrets.json: %s", e)
    try:
        renormalized = library.renormalize_cache()
        if renormalized:
            logger.info("Library cache: keys of %s tracks made again for this version", renormalized)
    except Exception as e:
        logger.error("Could not update the library cache's keys: %s", e)
    try:
        made = nd_accounts.ensure_initial()
        if made:
            logger.info("Navidrome account nd1 created from this install (user: %s)", made["username"] or "unknown")
    except Exception as e:
        logger.error("Could not set up the first Navidrome account: %s", e)
    try:
        made = deezer_accounts_from_secrets()
        if made:
            logger.info("%s Deezer accounts set up from this install", made)
    except Exception as e:
        logger.error("Could not set up the Deezer accounts: %s", e)
    try:
        given = playlist_accounts()
        if given:
            logger.info("%s playlists now belong to the first Navidrome account", given)
    except Exception as e:
        logger.error("Could not give the playlists to the first Navidrome account: %s", e)
    try:
        asked = playlist_covers()
        if asked:
            logger.info("%s Deezer playlists will ask Deezer for their cover again", asked)
    except Exception as e:
        logger.error("Could not check the playlists' covers: %s", e)
    try:
        if app_accounts():
            logger.info("The account of this install is now its Super-Admin")
    except Exception as e:
        logger.error("Could not set up the accounts of this app: %s", e)
