"""Field encryption and password hashing helpers."""

import hashlib
import hmac
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

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


def hash_vip_number(phone_number: str, encryption_key: str | bytes) -> str:
    """Return a stable keyed hash of a normalized phone number."""
    if len(phone_number) == 64 and all(char in "0123456789abcdef" for char in phone_number):
        return phone_number

    digits = re.sub(r"[^0-9]", "", phone_number)
    if not digits:
        raise ValueError("VIP phone number must contain digits")

    key = encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"callagent/vip-number-hmac/v1",
    ).derive(key)
    return hmac.new(derived_key, digits.encode("ascii"), hashlib.sha256).hexdigest()
