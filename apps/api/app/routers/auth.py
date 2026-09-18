import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.core.redis import get_redis
from app.core.security import hash_password
from app.db.session import get_db
from app.deps import REFRESH_COOKIE, current_user
from app.models import OAuthAccount, User
from app.schemas import AgeConfirmIn, AuthOut, EmailIn, LoginIn, Message, PasswordResetIn, RegisterIn, TokenIn, UserOut
from app.services import auth_service as auth
from app.services import email as mail
from app.services.audit import audit
from app.services.users import user_out

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
auth_limit = rate_limit("auth", settings.rate_limit_auth, fail_closed=True)

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL, not a secret
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
_jwks_client: jwt.PyJWKClient | None = None


async def _auth_out(db: AsyncSession, user: User, csrf: str) -> AuthOut:
    return AuthOut(user=await user_out(db, user), csrf_token=csrf,
                   access_token_expires_in=settings.access_token_minutes * 60)


@router.post("/register", response_model=Message, status_code=201, dependencies=[Depends(auth_limit)])
async def register(body: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)) -> Message:
    email = auth.normalise_email(body.email)
    generic = Message(message="If this address can be registered, a confirmation email is on its way.")
    if (await db.execute(select(User.id).where(User.email == email))).first():
        await audit(db, "register_existing_email", request)
        await db.commit()
        return generic  # do not reveal whether the account exists
    now = datetime.now(UTC)
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(),
                country=body.country, age_confirmed_at=now)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return generic
    token = await auth.create_email_token(db, user, "verify")
    await audit(db, "register", request, user.id)
    await db.commit()
    await mail.send_verification(email, token)
    return generic


@router.post("/verify-email", response_model=Message, dependencies=[Depends(auth_limit)])
async def verify_email(body: TokenIn, request: Request, db: AsyncSession = Depends(get_db)) -> Message:
    user = await auth.consume_email_token(db, body.token, "verify")
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await audit(db, "email_verified", request, user.id)
    await db.commit()
    return Message(message="Email confirmed. You can sign in now.")


@router.post("/resend-verification", response_model=Message, dependencies=[Depends(auth_limit)])
async def resend_verification(body: EmailIn, db: AsyncSession = Depends(get_db)) -> Message:
    user = (await db.execute(select(User).where(User.email == auth.normalise_email(body.email)))).scalar_one_or_none()
    if user and user.email_verified_at is None:
        token = await auth.create_email_token(db, user, "verify")
        await db.commit()
        await mail.send_verification(user.email, token)
    return Message(message="If the address needs confirming, a new email is on its way.")


@router.post("/login", response_model=AuthOut, dependencies=[Depends(auth_limit)])
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> AuthOut:
    user = await auth.authenticate(db, request, body.email, body.password)
    csrf = await auth.issue_session(db, request, response, user)
    return await _auth_out(db, user, csrf)


@router.post("/refresh", response_model=AuthOut)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> AuthOut:
    user, csrf = await auth.rotate_refresh(db, request, response, request.cookies.get(REFRESH_COOKIE))
    return await _auth_out(db, user, csrf)


@router.post("/logout", response_model=Message)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Message:
    await auth.revoke_refresh(db, request.cookies.get(REFRESH_COOKIE))
    auth.clear_session(response)
    return Message(message="Signed out.")


@router.post("/logout-all", response_model=Message)
async def logout_all(request: Request, response: Response, user: User = Depends(current_user),
                     db: AsyncSession = Depends(get_db)) -> Message:
    await auth.revoke_all_sessions(db, user.id)
    await audit(db, "logout_all", request, user.id)
    await db.commit()
    auth.clear_session(response)
    return Message(message="Signed out everywhere.")


@router.post("/password/forgot", response_model=Message, dependencies=[Depends(auth_limit)])
async def forgot_password(body: EmailIn, request: Request, db: AsyncSession = Depends(get_db)) -> Message:
    user = (await db.execute(select(User).where(User.email == auth.normalise_email(body.email)))).scalar_one_or_none()
    if user and user.is_active:
        token = await auth.create_email_token(db, user, "reset")
        await audit(db, "password_reset_requested", request, user.id)
        await db.commit()
        await mail.send_password_reset(user.email, token)
    return Message(message="If an account exists for that address, a reset link is on its way.")


@router.post("/password/reset", response_model=Message, dependencies=[Depends(auth_limit)])
async def reset_password(body: PasswordResetIn, request: Request, response: Response,
                         db: AsyncSession = Depends(get_db)) -> Message:
    user = await auth.consume_email_token(db, body.token, "reset")
    user.password_hash = hash_password(body.password)
    user.failed_logins, user.locked_until = 0, None
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)  # the link proves the address
    await auth.revoke_all_sessions(db, user.id)
    await audit(db, "password_reset", request, user.id)
    await db.commit()
    auth.clear_session(response)
    return Message(message="Password changed. Sign in with your new password.")


@router.post("/confirm-age", response_model=UserOut)
async def confirm_age(body: AgeConfirmIn, request: Request, user: User = Depends(current_user),
                      db: AsyncSession = Depends(get_db)) -> UserOut:
    user.age_confirmed_at = user.age_confirmed_at or datetime.now(UTC)
    await audit(db, "age_confirmed", request, user.id)
    await db.commit()
    return await user_out(db, user)


# ---------------------------------------------------------------------------------------------- Google OAuth
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@router.get("/google/start", dependencies=[Depends(auth_limit)])
async def google_start() -> RedirectResponse:
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not configured")
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    await get_redis().set(f"oauth:google:{state}", json.dumps({"nonce": nonce, "verifier": verifier}), ex=600)
    params = httpx.QueryParams({
        "client_id": settings.google_client_id, "response_type": "code", "scope": "openid email profile",
        "redirect_uri": f"{settings.public_api_url}{settings.api_prefix}/auth/google/callback",
        "state": state, "nonce": nonce, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256", "prompt": "select_account"})
    return RedirectResponse(f"{GOOGLE_AUTH}?{params}", status_code=302)


def _verify_google_id_token(token: str, nonce: str) -> dict:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(GOOGLE_JWKS, cache_keys=True)
    key = _jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=settings.google_client_id,
                        issuer=["https://accounts.google.com", "accounts.google.com"])
    if claims.get("nonce") != nonce:
        raise jwt.InvalidTokenError("nonce mismatch")
    return claims


@router.get("/google/callback", dependencies=[Depends(auth_limit)])
async def google_callback(request: Request, code: str = "", state: str = "",
                          db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    import asyncio
    fail = RedirectResponse(f"{settings.public_web_url}/login?error=google", status_code=302)
    stored = await get_redis().getdel(f"oauth:google:{state}") if state else None
    if not code or not stored:
        return fail
    data = json.loads(stored)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(GOOGLE_TOKEN, data={
            "code": code, "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "redirect_uri": f"{settings.public_api_url}{settings.api_prefix}/auth/google/callback",
            "grant_type": "authorization_code", "code_verifier": data["verifier"]})
    if r.status_code != 200 or "id_token" not in r.json():
        return fail
    try:
        claims = await asyncio.to_thread(_verify_google_id_token, r.json()["id_token"], data["nonce"])
    except jwt.PyJWTError:
        return fail
    if not claims.get("email_verified"):
        return fail
    email = auth.normalise_email(claims["email"])
    link = (await db.execute(select(OAuthAccount).where(OAuthAccount.provider == "google",
                                                        OAuthAccount.subject == claims["sub"]))).scalar_one_or_none()
    user = await db.get(User, link.user_id) if link else None
    if user is None:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, full_name=claims.get("name", "")[:120], password_hash=None)
            db.add(user)
            await db.flush()
        db.add(OAuthAccount(user_id=user.id, provider="google", subject=claims["sub"]))
    if not user.is_active:
        return fail
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await audit(db, "login_google", request, user.id)
    target = "/dashboard" if user.age_confirmed_at else "/onboarding"
    response = RedirectResponse(f"{settings.public_web_url}{target}", status_code=302)
    await auth.issue_session(db, request, response, user)
    return response
