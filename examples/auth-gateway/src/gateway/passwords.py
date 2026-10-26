import hashlib
import hmac
import os

from gateway.errors import WeakPassword

MIN_LENGTH = 12


def validate(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPassword("too short")
    if not any(ch.isdigit() for ch in password):
        raise WeakPassword("needs a digit")


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt, digest


def verify(password: str, salt: bytes, digest: bytes) -> bool:
    _, candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, digest)
