"""Two-factor sign-in: TOTP (RFC 6238: HMAC-SHA1, 6 digits, 30 s steps) and single-use recovery codes.

Authenticator secrets are stored encrypted (Fernet, MFA_ENCRYPTION_KEY); recovery codes only as SHA-256 digests.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import get_settings

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1                 # accept the previous and next step too (clock drift)
RECOVERY_CODES = 10
_RECOVERY_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # no I, L, O, U


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP over the time step (RFC 6238)."""
    mac = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def verify(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """The matching time step, or None. A step at or before `last_step` is refused, so a code works once."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now_step = current_step(now)
    for step in range(now_step - WINDOW, now_step + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?" + urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1",
                                                   "digits": DIGITS, "period": STEP_SECONDS})


# ------------------------------------------------------------------------------------------ recovery codes
def normalise_recovery(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def recovery_digest(code: str) -> str:
    return hashlib.sha256(normalise_recovery(code).encode()).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """(codes to show once as XXXXX-XXXXX, their digests to store). 50 bits each."""
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [recovery_digest(c) for c in codes]


def looks_like_recovery_code(code: str) -> bool:
    return len(normalise_recovery(code)) == 10 and not code.strip().isdigit()


# ------------------------------------------------------------------------------------------ secret storage
def _fernet() -> Fernet:
    key = get_settings().mfa_encryption_key.get_secret_value()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Two-factor sign-in is not configured")
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:  # key changed: the stored authenticator can no longer be read
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Two-factor sign-in is misconfigured") from e
