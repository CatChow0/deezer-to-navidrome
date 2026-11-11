"""Writing a file so that a reader never sees it half-written, and a crash never
leaves it cut short: the text goes to a temporary file next to it, which then
takes its place in one step."""

import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def write_atomic(path, text: str, private: bool = False) -> None:
    """`private`: readable by the owner only (secrets, tokens, keys)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own, so two writers at once never share a temporary file.
    fd, partial = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(partial, 0o600 if private else 0o644)
        except OSError:
            pass
        _replace(partial, path)
    except BaseException:
        try:
            os.unlink(partial)
        except OSError:
            pass
        raise


def write_json(path, data, private: bool = False) -> None:
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2), private=private)


def read_json(path, default):
    """The file's JSON, or `default` when it does not exist. A file that cannot be
    read is set aside (name.corrupt-<time>) before `default` is returned, so the
    next save does not write over what it held. A disk error is raised: the
    file may be fine, and saving `default` would lose it."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except ValueError as e:
        aside = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(path, aside)
            logger.error("%s could not be read (%s): set aside as %s", path, e, aside.name)
        except OSError:
            logger.error("%s could not be read (%s)", path, e)
        return default


def _replace(source, target, tries=20):
    # Windows refuses to replace a file another thread has open for a moment.
    for attempt in range(tries):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05)
