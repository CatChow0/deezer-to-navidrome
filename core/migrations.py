"""One-time changes to the data of an existing install, run at start-up.

Each step is safe to run again and never stops the app: a failure is logged
and the next start tries again."""
import logging

logger = logging.getLogger(__name__)


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
