"""Request dependencies: current user from cookie / bearer token / API key."""
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, token_digest
from app.db.session import get_db
from app.models import User

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
