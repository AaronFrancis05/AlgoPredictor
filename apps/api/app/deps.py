"""Request dependencies: current user from cookie / bearer token / API key.

Two flavours: `optional_user` / `current_user` load the full User row (account pages that read or change it);
`optional_viewer` / `verified_viewer` return a small cached snapshot for the read-heavy prediction endpoints,
so polling a pick list does not cost a database query per request.
"""
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached, forget
from app.core.logging import get_logger
from app.core.security import decode_access_token, token_digest
from app.db.session import get_db
from app.models import ROLE_ADMIN, User

log = get_logger(__name__)

ACCESS_COOKIE = "ap_access"
REFRESH_COOKIE = "ap_refresh"
CSRF_COOKIE = "ap_csrf"
CSRF_HEADER = "x-csrf-token"
API_KEY_HEADER = "x-api-key"


def bearer_or_cookie(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    api_key = request.headers.get(API_KEY_HEADER)
    if api_key:
        user = (await db.execute(select(User).where(User.api_key_digest == token_digest(api_key)))).scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        request.state.user_id = str(user.id)
        return user
    token = bearer_or_cookie(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user = await db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        return None
    request.state.user_id = str(user.id)
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


async def verified_adult(user: User = Depends(current_user)) -> User:
    """Predictions are only shown to verified, 18+ confirmed users."""
    if user.email_verified_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "email_not_verified"})
    if user.age_confirmed_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "age_not_confirmed"})
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


# ---------------------------------------------------------------------------------------------- cached viewer
VIEWER_CACHE_NS = "viewer"
VIEWER_TTL = 60  # upper bound on staleness if an invalidation is missed; changes below call forget_viewer()


@dataclass(frozen=True)
class Viewer:
    id: UUID
    email_verified: bool
    age_confirmed: bool
    role: str

    @property
    def verified_adult(self) -> bool:
        return self.email_verified and self.age_confirmed

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def viewer_of(user: User) -> Viewer:
    return Viewer(id=user.id, email_verified=user.email_verified_at is not None,
                  age_confirmed=user.age_confirmed_at is not None, role=user.role)


async def forget_viewer(user_id: UUID) -> None:
    """Call after changing a user's verification, age confirmation, role or active flag."""
    try:
        await forget(VIEWER_CACHE_NS, str(user_id))
    except Exception as e:  # the TTL still bounds staleness
        log.warning("viewer_forget_failed", error=str(e))


async def optional_viewer(request: Request, db: AsyncSession = Depends(get_db)) -> Viewer | None:
    """Like optional_user, but a session token is resolved from the cache (inactive accounts are cached as None).
    API keys still read the database: they are rare and are revoked by clearing the digest."""
    if request.headers.get(API_KEY_HEADER):
        user = await optional_user(request, db)
        return viewer_of(user) if user else None
    token = bearer_or_cookie(request)
    if not token:
        return None
    try:
        user_id = UUID(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, ValueError):
        return None

    async def load() -> dict | None:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        v = viewer_of(user)
        return dict(email_verified=v.email_verified, age_confirmed=v.age_confirmed, role=v.role)

    data = await cached(VIEWER_CACHE_NS, str(user_id), VIEWER_TTL, load)
    if data is None:
        return None
    request.state.user_id = str(user_id)
    return Viewer(id=user_id, **data)


async def verified_viewer(viewer: Viewer | None = Depends(optional_viewer)) -> Viewer:
    """verified_adult for the cached viewer."""
    if viewer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    if not viewer.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "email_not_verified"})
    if not viewer.age_confirmed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "age_not_confirmed"})
    return viewer
