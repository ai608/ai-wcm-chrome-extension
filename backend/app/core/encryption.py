# Copied from AI Lead Pipeline backend app/core/encryption.py, trimmed for the Sales Assistant.
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_ENC_PREFIX = "enc:"


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY.strip()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not set in the environment.")
    return Fernet(key.encode())


def decrypt_value(value: str) -> str:
    """Decrypt a previously encrypted string (must include the enc: prefix)."""
    if not value.startswith(_ENC_PREFIX):
        raise ValueError("Value does not appear to be an encrypted token.")
    raw = value[len(_ENC_PREFIX) :]
    f = _get_fernet()
    try:
        return f.decrypt(raw.encode()).decode()
    except (InvalidToken, TypeError) as exc:
        raise ValueError(
            "Failed to decrypt value — invalid key or tampered data."
        ) from exc
