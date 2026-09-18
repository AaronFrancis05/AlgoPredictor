"""Password hashing, JWT access tokens, opaque refresh/email tokens, CSRF and HMAC helpers."""
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id with the library's recommended parameters


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: UUID, plan: str, mfa: bool = False) -> str:
    """`mfa` records that this session was started with a second factor (required for admin endpoints)."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "plan": plan, "type": "access", "mfa": mfa, "iat": now,
               "exp": now + timedelta(minutes=s.access_token_minutes), "jti": secrets.token_hex(8)}
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret.get_secret_value(), algorithms=[s.jwt_algorithm],
                         options={"require": ["exp", "sub", "type"]})
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> str:
    """Tokens are stored only as SHA-256 digests."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signed_payload(secret: str, timestamp: str, body: bytes, signature: str, max_skew: int) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts) > max_skew:
        return False
    return hmac.compare_digest(sign_payload(secret, timestamp, body), signature or "")
