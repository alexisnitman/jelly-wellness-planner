"""Encryption for secrets we choose to store (the remembered private calendar link). Fernet = AES-128-CBC + HMAC.

Key source: the APP_ENCRYPTION_KEY environment variable, else a key file backend/data/app.key created on first
use (mode 0600, git-ignored). A key file next to the database protects against a leaked database or backup but
NOT against someone who can read the whole data folder; set APP_ENCRYPTION_KEY in a .env elsewhere for more.
"""

from __future__ import annotations

import os
import stat
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

import store


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    env = os.getenv("APP_ENCRYPTION_KEY", "").strip()
    if env:
        return Fernet(env.encode())
    key_path = store.DATA_DIR / "app.key"
    if not key_path.exists():
        store.DATA_DIR.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
    return Fernet(key_path.read_bytes().strip())


def reset_cache() -> None:
    _fernet.cache_clear()


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
