"""Encryption of the credentials kept in the data folder: Navidrome accounts and
secrets.json (Deezer ARLs, tokens).

AES-256-GCM, with pycryptodome (already used to decrypt downloads). The key
comes from D2N_ENCRYPTION_KEY. Without it, a key is generated in
DATA_DIR/encryption.key: that still protects a settings file copied on its own,
but not a copy of the whole data folder, which carries the key along.

Encrypted values look like "enc:v1:<base64url(nonce | ciphertext | tag)>".
A value without that prefix is returned as it is, so files written by older
versions keep working until they are encrypted at start-up."""
import base64
import binascii
import hashlib
import logging
import os
import re
import secrets
import threading
from pathlib import Path

from Crypto.Cipher import AES

from core import config

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
KEY_ENV = "D2N_ENCRYPTION_KEY"
NONCE_BYTES = 12
TAG_BYTES = 16
_derived = {}
_lock = threading.Lock()


class DecryptError(ValueError):
    """The value was encrypted with a key this install no longer has."""


def key_file() -> Path:
    return Path(config.DATA_DIR) / "encryption.key"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(value: str) -> bytes:
    """A 32-byte key, or any passphrase stretched into one."""
    with _lock:
        if value in _derived:
            return _derived[value]
    try:
        raw = _b64decode(value)
    except (ValueError, binascii.Error):
        raw = b""
    key = raw if len(raw) == 32 else hashlib.scrypt(
        value.encode(), salt=b"deezer-to-navidrome/encryption/v1", n=2 ** 14, r=8, p=1, dklen=32)
    with _lock:
        _derived[value] = key
    return key


def _env_key():
    value = os.environ.get(KEY_ENV, "").strip()
    return _derive(value) if value else None


def _file_key(create: bool):
    path = key_file()
    try:
        return _b64decode(path.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        pass
    except (OSError, ValueError, binascii.Error) as e:
        logger.error("The encryption key file could not be read: %s", e)
        return None
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    partial = path.with_name(f".{path.name}.part")
    partial.write_text(_b64encode(key) + "\n", encoding="utf-8")
    try:
        partial.chmod(0o600)
    except OSError:
        pass
    os.replace(partial, path)
    logger.warning("No %s: generated an encryption key in %s", KEY_ENV, path)
    return key


def _keys():
    """The key new values use, then every key that may have written old ones."""
    env_key = _env_key()
    file_key = _file_key(create=env_key is None)
    primary = env_key or file_key
    return primary, [key for key in (env_key, file_key) if key]


def key_source() -> str:
    """"env" when D2N_ENCRYPTION_KEY is set, else "file"."""
    return "env" if os.environ.get(KEY_ENV, "").strip() else "file"


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(text: str) -> str:
    if not text:
        return ""
    primary, _ = _keys()
    nonce = secrets.token_bytes(NONCE_BYTES)
    cipher = AES.new(primary, AES.MODE_GCM, nonce=nonce)
    body, tag = cipher.encrypt_and_digest(text.encode("utf-8"))
    return PREFIX + _b64encode(nonce + body + tag)


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        return value or ""
    try:
        data = _b64decode(value[len(PREFIX):])
    except (ValueError, binascii.Error) as e:
        raise DecryptError("This value is damaged") from e
    if len(data) < NONCE_BYTES + TAG_BYTES:
        raise DecryptError("This value is damaged")
    nonce, body, tag = data[:NONCE_BYTES], data[NONCE_BYTES:-TAG_BYTES], data[-TAG_BYTES:]
    for key in _keys()[1]:
        try:
            return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(body, tag).decode("utf-8")
        except ValueError:
            continue
    raise DecryptError("This value was encrypted with another key")


def needs_rewrap(value) -> bool:
    """Plain, or encrypted with a key other than the one in use now."""
    if not value:
        return False
    if not is_encrypted(value):
        return True
    primary, _ = _keys()
    data = _b64decode(value[len(PREFIX):])
    try:
        AES.new(primary, AES.MODE_GCM, nonce=data[:NONCE_BYTES]).decrypt_and_verify(
            data[NONCE_BYTES:-TAG_BYTES], data[-TAG_BYTES:])
        return False
    except ValueError:
        return True


_SECRET_PARAMS = re.compile(r"(?i)\b(p|t|s|apikey|api_key|token|password|arl)=([^&\s\"']+)")


def redact(text, *values) -> str:
    """The text with every given secret, and every credential-like URL
    parameter, replaced by ***. For error messages and logs."""
    text = str(text or "")
    for value in values:
        if value and len(str(value)) >= 4:
            text = text.replace(str(value), "***")
    return _SECRET_PARAMS.sub(lambda m: f"{m.group(1)}=***", text)
