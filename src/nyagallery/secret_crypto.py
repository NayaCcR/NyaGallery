from __future__ import annotations

import base64
import hashlib
import os
import secrets


SECRET_KEY_ENV = "NYAGALLERY_SECRET_KEY"
ENCRYPTED_SECRET_PREFIX = "nyaenc:v1:"


class SecretEncryptionError(ValueError):
    """Raised when an encrypted secret cannot be decrypted with the current key."""


def generate_secret_key() -> str:
    """Return a Fernet-compatible 256-bit key for NYAGALLERY_SECRET_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def configured_secret_key(explicit_key: str | None = None) -> str:
    return (os.environ.get(SECRET_KEY_ENV) or explicit_key or "").strip()


def secret_encryption_enabled(explicit_key: str | None = None) -> bool:
    return bool(configured_secret_key(explicit_key))


def is_encrypted_secret(value: str | None) -> bool:
    return bool(value and value.startswith(ENCRYPTED_SECRET_PREFIX))


def encrypt_secret(value: str | None, explicit_key: str | None = None) -> str:
    text = value or ""
    if not text or is_encrypted_secret(text):
        return text
    key = configured_secret_key(explicit_key)
    if not key:
        return text
    token = _fernet(key).encrypt(text.encode("utf-8")).decode("ascii")
    return ENCRYPTED_SECRET_PREFIX + token


def decrypt_secret(value: str | None, explicit_key: str | None = None) -> str:
    text = value or ""
    if not is_encrypted_secret(text):
        return text
    key = configured_secret_key(explicit_key)
    if not key:
        raise SecretEncryptionError(
            f"encrypted secret requires {SECRET_KEY_ENV}; set the same key used when the secret was saved"
        )
    token = text[len(ENCRYPTED_SECRET_PREFIX):]
    try:
        return _fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as exc:  # cryptography raises InvalidToken for wrong keys/corrupt data.
        raise SecretEncryptionError("encrypted secret could not be decrypted with the current secret key") from exc


def _fernet(key: str):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise SecretEncryptionError(
            "encrypted secrets require the cryptography package; install NyaGallery dependencies again"
        ) from exc
    return Fernet(_fernet_key(key))


def _fernet_key(value: str) -> bytes:
    text = value.strip()
    try:
        decoded = base64.urlsafe_b64decode(_padded_base64(text).encode("ascii"))
        if len(decoded) == 32:
            return base64.urlsafe_b64encode(decoded)
    except (ValueError, UnicodeEncodeError):
        pass
    digest = hashlib.sha256(f"NyaGallery secret key\0{text}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _padded_base64(value: str) -> str:
    return value + ("=" * (-len(value) % 4))
