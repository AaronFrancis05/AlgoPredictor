"""Account lifecycle: registration, login with lockout, refresh-token rotation, email tokens."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import client_ip
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    new_csrf_token,
    new_opaque_token,
    token_digest,
    verify_password,
)
from app.deps import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    user.failed_logins, user.locked_until = 0, None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await audit(db, "login", request, user.id)
    return user


async def issue_session(db: AsyncSession, request: Request, response: Response, user: User,
                        family_id: uuid.UUID | None = None) -> str:
    """Create access + refresh cookies and a CSRF cookie. Returns the CSRF token."""
    s = get_settings()
    plan = await active_plan(db, user.id)
    access = create_access_token(user.id, plan.code)
    refresh = new_opaque_token()
    db.add(RefreshToken(user_id=user.id, token_digest=token_digest(refresh), family_id=family_id or uuid.uuid4(),
                        expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
                        user_agent=(request.headers.get("user-agent") or "")[:200], ip=client_ip(request)))
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


async def rotate_refresh(db: AsyncSession, request: Request, response: Response, token: str | None) -> tuple[User, str]:
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
    csrf = await issue_session(db, request, response, user, family_id=row.family_id)
    return user, csrf


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
