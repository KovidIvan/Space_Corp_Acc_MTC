"""Field encryption and password hashing helpers."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet

_password_hasher = PasswordHasher()


def _fernet(key: str | bytes) -> Fernet:
    """Create a Fernet instance from a URL-safe base64 key."""
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_text(value: str, key: str | bytes) -> str:
    """Encrypt UTF-8 text and return a Fernet token."""
    return _fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(token: str, key: str | bytes) -> str:
    """Decrypt a Fernet token to UTF-8 text."""
    return _fernet(key).decrypt(token.encode("ascii")).decode("utf-8")


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password hash without raising for an invalid or mismatched hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
