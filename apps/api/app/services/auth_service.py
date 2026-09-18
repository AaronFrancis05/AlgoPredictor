"""Account lifecycle: registration, login with lockout, two-factor challenge, refresh-token rotation, email tokens."""
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import totp
from app.core.config import get_settings
from app.core.ratelimit import client_ip
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    new_csrf_token,
    new_opaque_token,
    token_digest,
    verify_password,
)
from app.deps import ACCESS_COOKIE, CSRF_COOKIE, MFA_COOKIE, REFRESH_COOKIE
from app.models import EmailToken, RefreshToken, User
from app.services.audit import audit
from app.services.entitlements import active_plan

# a real Argon2 hash used to equalise timing when the email does not exist
_DUMMY_HASH = hash_password("not-a-real-password-Aa1!")


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def create_email_token(db: AsyncSession, user: User, purpose: str) -> str:
    token = new_opaque_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_digest=token_digest(token),
                      expires_at=datetime.now(UTC) + timedelta(hours=get_settings().email_token_hours)))
    return token


async def consume_email_token(db: AsyncSession, token: str, purpose: str) -> User:
    row = (await db.execute(select(EmailToken).where(EmailToken.token_digest == token_digest(token),
                                                     EmailToken.purpose == purpose))).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or _as_aware(row.expires_at) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")
    row.used_at = now
    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")
    return user


async def authenticate(db: AsyncSession, request: Request, email: str, password: str) -> User:
    s = get_settings()
    user = (await db.execute(select(User).where(User.email == normalise_email(email)))).scalar_one_or_none()
    now = datetime.now(UTC)
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if user is None or user.password_hash is None:
        verify_password(_DUMMY_HASH, password)
        await audit(db, "login_failed", request, reason="unknown_or_oauth_only")
        await db.commit()
        raise generic
    if user.locked_until and _as_aware(user.locked_until) > now:
        await audit(db, "login_locked", request, user.id)
        await db.commit()
        raise HTTPException(status.HTTP_423_LOCKED, "Account temporarily locked. Try again later.")
    if not verify_password(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= s.max_login_failures:
            # exponential backoff: 15, 30, 60 ... minutes, capped at 24h
            extra = user.failed_logins - s.max_login_failures
            user.locked_until = now + timedelta(minutes=min(s.lockout_minutes * 2 ** extra, 1440))
        await audit(db, "login_failed", request, user.id, failures=user.failed_logins)
        await db.commit()
        raise generic
    if not user.is_active:
        # only reached with the right password, so this reveals nothing to someone guessing addresses
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "This account is closed. Contact support if you want it restored before it is erased."
                            if user.deleted_at else "Account disabled")
    user.failed_logins, user.locked_until = 0, None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await audit(db, "login", request, user.id)
    return user


async def issue_session(db: AsyncSession, request: Request, response: Response, user: User,
                        family_id: uuid.UUID | None = None, mfa: bool = False) -> str:
    """Create access + refresh cookies and a CSRF cookie. Returns the CSRF token.
    `mfa`: the session was started with a second factor (kept through refresh rotation)."""
    s = get_settings()
    plan = await active_plan(db, user.id)
    access = create_access_token(user.id, plan.code, mfa=mfa)
    refresh = new_opaque_token()
    db.add(RefreshToken(user_id=user.id, token_digest=token_digest(refresh), family_id=family_id or uuid.uuid4(),
                        expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
                        user_agent=(request.headers.get("user-agent") or "")[:200], ip=client_ip(request), mfa=mfa))
    await db.commit()
    csrf = new_csrf_token()
    common = dict(secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain)
    response.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_minutes * 60, httponly=True, path="/",
                        **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=s.refresh_token_days * 86400, httponly=True,
                        path="/api/v1/auth", **common)
    response.set_cookie(CSRF_COOKIE, csrf, max_age=s.refresh_token_days * 86400, httponly=False, path="/",
                        **common)
    return csrf


def clear_session(response: Response) -> None:
    s = get_settings()
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, "/api/v1/auth"), (CSRF_COOKIE, "/")):
        response.delete_cookie(name, path=path, domain=s.cookie_domain)


async def rotate_refresh(db: AsyncSession, request: Request, response: Response,
                         token: str | None) -> tuple[User, str, bool]:
    """Returns (user, csrf, mfa) where mfa says whether the new session carries the second factor."""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No session")
    row = (await db.execute(select(RefreshToken).where(RefreshToken.token_digest == token_digest(token)))
           ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if row.rotated_at is not None or row.revoked_at is not None:
        # reuse of an old token: assume theft, revoke the whole family
        await db.execute(update(RefreshToken).where(RefreshToken.family_id == row.family_id,
                                                    RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        await audit(db, "refresh_reuse_detected", request, row.user_id)
        await db.commit()
        clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    if _as_aware(row.expires_at) < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    row.rotated_at = now
    # a session started with two-factor stays that way only while the account still has two-factor on
    mfa = bool(row.mfa) and user.mfa_enabled
    csrf = await issue_session(db, request, response, user, family_id=row.family_id, mfa=mfa)
    return user, csrf, mfa


async def revoke_refresh(db: AsyncSession, token: str | None) -> None:
    if not token:
        return
    row = (await db.execute(select(RefreshToken).where(RefreshToken.token_digest == token_digest(token)))
           ).scalar_one_or_none()
    if row is not None:
        await db.execute(update(RefreshToken).where(RefreshToken.family_id == row.family_id,
                                                    RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=datetime.now(UTC)))
        await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=datetime.now(UTC)))


# ---------------------------------------------------------------------------------------------- two-factor
MFA_COOKIE_PATH = "/api/v1/auth/mfa"
MFA_CHALLENGE_SECONDS = 300
MFA_CHALLENGE_ATTEMPTS = 5


def _challenge_key(token: str) -> str:
    return f"mfa:challenge:{token_digest(token)}"


def clear_mfa_challenge(response: Response) -> None:
    response.delete_cookie(MFA_COOKIE, path=MFA_COOKIE_PATH, domain=get_settings().cookie_domain)


async def start_mfa_challenge(response: Response, user: User, via: str) -> None:
    """The first factor passed: instead of a session, the browser gets an HttpOnly challenge cookie (5 minutes,
    only sent to /auth/mfa) that POST /auth/mfa/verify exchanges for a session with the second factor."""
    s = get_settings()
    token = new_opaque_token()
    await get_redis().set(_challenge_key(token), json.dumps({"user_id": str(user.id), "via": via, "attempts": 0}),
                          ex=MFA_CHALLENGE_SECONDS)
    response.set_cookie(MFA_COOKIE, token, max_age=MFA_CHALLENGE_SECONDS, httponly=True, path=MFA_COOKIE_PATH,
                        secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain)


def check_second_factor(user: User, code: str) -> str | None:
    """"totp" or "recovery" when `code` is valid (and consumes it on `user`), else None. Caller commits."""
    if not user.mfa_enabled or not user.totp_secret_enc:
        return None
    if totp.looks_like_recovery_code(code):
        digest = totp.recovery_digest(code)
        remaining = list(user.mfa_recovery_digests or [])
        if digest in remaining:
            remaining.remove(digest)
            user.mfa_recovery_digests = remaining  # reassign so the JSON column is marked changed
            return "recovery"
        return None
    step = totp.verify(totp.decrypt_secret(user.totp_secret_enc), code, user.totp_last_step)
    if step is None:
        return None
    user.totp_last_step = step
    return "totp"


async def complete_mfa_challenge(db: AsyncSession, request: Request, response: Response,
                                 code: str) -> tuple[User, str]:
    """Exchange the challenge cookie + a TOTP or recovery code for a session marked mfa=True. Returns (user, csrf)."""
    s = get_settings()
    redis = get_redis()
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "mfa_expired"})
    token = request.cookies.get(MFA_COOKIE)
    raw = await redis.get(_challenge_key(token)) if token else None
    if not raw:
        raise expired
    data = json.loads(raw)
    user = (await db.execute(select(User).where(User.id == uuid.UUID(data["user_id"])).with_for_update())
            ).scalar_one_or_none()
    if user is None or not user.is_active or not user.mfa_enabled:
        await redis.delete(_challenge_key(token))
        raise expired
    fails_key = f"mfa:fail:{user.id}"
    if int(await redis.get(fails_key) or 0) >= s.mfa_max_failures:
        await audit(db, "mfa_locked", request, user.id)
        await db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "mfa_locked"},
                            headers={"Retry-After": str(s.mfa_lockout_minutes * 60)})
    method = check_second_factor(user, code)
    if method is None:
        await redis.incr(fails_key)
        await redis.expire(fails_key, s.mfa_lockout_minutes * 60)
        data["attempts"] += 1
        if data["attempts"] >= MFA_CHALLENGE_ATTEMPTS:
            await redis.delete(_challenge_key(token))  # sign in with the password again
        else:
            await redis.set(_challenge_key(token), json.dumps(data), keepttl=True)
        await audit(db, "mfa_failed", request, user.id, via=data["via"])
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "mfa_invalid"})
    await redis.delete(_challenge_key(token))
    await redis.delete(fails_key)
    await audit(db, "login_mfa", request, user.id, via=data["via"], method=method,
                recovery_codes_left=len(user.mfa_recovery_digests or []) if method == "recovery" else None)
    csrf = await issue_session(db, request, response, user, mfa=True)
    clear_mfa_challenge(response)
    return user, csrf
