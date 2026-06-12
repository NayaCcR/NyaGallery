from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import secrets


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "guest": frozenset({"view"}),
    "viewer": frozenset({"view", "download", "api"}),
    "editor": frozenset({"view", "download", "api", "upload", "edit_tags", "delete_request"}),
    "admin": frozenset({"view", "download", "api", "upload", "edit_tags", "delete_request", "delete", "admin"}),
    "developer": frozenset({
        "view",
        "download",
        "api",
        "upload",
        "edit_tags",
        "delete_request",
        "delete",
        "admin",
        "developer",
        "config",
        "console",
    }),
}


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
TOKEN_PREFIX = "nya_"
SESSION_PREFIX = "nys_"
CSRF_PREFIX = "nyc_"


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    user_id: int | None = None

    def has_permission(self, permission: str) -> bool:
        return permission in permissions_for_role(self.role)


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ROLE_PERMISSIONS:
        valid = ", ".join(sorted(ROLE_PERMISSIONS))
        raise ValueError(f"invalid role {role!r}; expected one of: {valid}")
    return normalized


def hash_secret(secret: str, *, salt: bytes | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    if not secret:
        raise ValueError("secret cannot be empty")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt_bytes, iterations)
    return "$".join(
        (
            PASSWORD_ALGORITHM,
            str(iterations),
            base64.urlsafe_b64encode(salt_bytes).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_secret(secret: str, secret_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = secret_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_opaque_token(token: str) -> str:
    if not token:
        raise ValueError("token cannot be empty")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_opaque_token(token: str, token_hash: str) -> bool:
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_opaque_token(token), token_hash)


def hash_password(password: str) -> str:
    return hash_secret(password)


def verify_password(password: str, password_hash: str) -> bool:
    return verify_secret(password, password_hash)


def generate_api_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def generate_session_token() -> str:
    return SESSION_PREFIX + secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return CSRF_PREFIX + secrets.token_urlsafe(32)


def token_prefix(token: str) -> str:
    return token[:16]
