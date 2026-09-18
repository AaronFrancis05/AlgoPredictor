"""Account self-service: profile, follows, API key (Elite), data export and deletion."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.core.security import hash_password, new_opaque_token, token_digest, verify_password
from app.db.session import get_db
from app.deps import current_user, forget_viewer, verified_adult
from app.models import AuditLog, OAuthAccount, Payment, Slip, Subscription, User, UserFollow
from app.routers.auth import google_authorize_url
from app.schemas import ApiKeyOut, FollowsOut, GoogleLinkOut, Message, PasswordSetIn, RedeemIn, UserOut
from app.services import access_tokens
from app.services import auth_service as auth
from app.services.audit import audit
from app.services.entitlements import require_entitlement
from app.services.users import close_account, user_out

router = APIRouter(prefix="/me", tags=["account"])
settings = get_settings()
auth_limit = rate_limit("auth", settings.rate_limit_auth, fail_closed=True)


@router.get("", response_model=UserOut)
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> UserOut:
    return await user_out(db, user)


# ------------------------------------------------------------------ sign-in methods (password and Google)
@router.post("/password", response_model=Message, dependencies=[Depends(auth_limit)])
async def set_password(body: PasswordSetIn, request: Request, response: Response, user: User = Depends(current_user),
                       db: AsyncSession = Depends(get_db)) -> Message:
    """Add a password to a Google-only account, or change it (needs the current one).
    Every other session is signed out; this browser gets a fresh session."""
    had_password = user.password_hash is not None
    if had_password and not (body.current_password and verify_password(user.password_hash, body.current_password)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.password)
    user.failed_logins, user.locked_until = 0, None
    await auth.revoke_all_sessions(db, user.id)
    await audit(db, "password_changed" if had_password else "password_added", request, user.id)
    await auth.issue_session(db, request, response, user)
    return Message(message="Password changed." if had_password else
                   "Password added. You can now sign in with your email and password as well as Google.")


@router.post("/google/link", response_model=GoogleLinkOut, dependencies=[Depends(auth_limit)])
async def link_google(user: User = Depends(current_user)) -> GoogleLinkOut:
    """Start connecting a Google account. The browser then navigates to the returned URL."""
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not available yet")
    return GoogleLinkOut(url=await google_authorize_url(link_user_id=user.id))


@router.delete("/google", response_model=Message)
async def unlink_google(request: Request, user: User = Depends(current_user),
                        db: AsyncSession = Depends(get_db)) -> Message:
    if user.password_hash is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Add a password first, so you can still sign in after Google is disconnected")
    await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == user.id, OAuthAccount.provider == "google"))
    await audit(db, "google_unlinked", request, user.id)
    await db.commit()
    return Message(message="Google disconnected. Sign in with your email and password from now on.")


@router.post("/access-token", response_model=Message, dependencies=[Depends(auth_limit)])
async def redeem_access_token(body: RedeemIn, request: Request, user: User = Depends(verified_adult),
                              db: AsyncSession = Depends(get_db)) -> Message:
    """Redeem an admin-issued code: the token's plan until the token expires. Rate limited like sign-in, so
    codes cannot be guessed by brute force."""
    sub = await access_tokens.redeem(db, user, body.code)
    await audit(db, "access_token_redeemed", request, user.id, token=str(sub.access_token_id), plan=sub.plan_code)
    await db.commit()
    await access_tokens.after_change()
    return Message(message=f"Code accepted. You have the {sub.plan_code.capitalize()} plan until "
                           f"{sub.current_period_end:%d %B %Y, %H:%M} UTC.")


@router.post("/api-key", response_model=ApiKeyOut, dependencies=[Depends(require_entitlement("api_access"))])
async def create_api_key(request: Request, user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)) -> ApiKeyOut:
    """Create (or replace) the account's API key. Only its SHA-256 digest is stored."""
    key = "ap_" + new_opaque_token()
    user.api_key_digest = token_digest(key)
    await audit(db, "api_key_created", request, user.id)
    await db.commit()
    return ApiKeyOut(api_key=key)


@router.delete("/api-key", response_model=Message)
async def delete_api_key(request: Request, user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)) -> Message:
    user.api_key_digest = None
    await audit(db, "api_key_deleted", request, user.id)
    await db.commit()
    return Message(message="API key deleted.")


# ------------------------------------------------------------------ follows (matches and leagues)
MAX_FOLLOWS = 300
FOLLOW_TARGET = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


async def _follows(db: AsyncSession, user_id) -> FollowsOut:
    rows = (await db.execute(select(UserFollow.kind, UserFollow.target).where(UserFollow.user_id == user_id)
                             .order_by(UserFollow.created_at))).all()
    return FollowsOut(matches=[t for k, t in rows if k == "match"], leagues=[t for k, t in rows if k == "league"])


@router.get("/follows", response_model=FollowsOut)
async def list_follows(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> FollowsOut:
    return await _follows(db, user.id)


@router.put("/follows/{kind}/{target}", response_model=FollowsOut)
async def follow(kind: Literal["match", "league"], target: str, user: User = Depends(current_user),
                 db: AsyncSession = Depends(get_db)) -> FollowsOut:
    """Follow a match (its prediction_id) or a league (its code). Idempotent."""
    if not FOLLOW_TARGET.match(target):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid follow target")
    exists = await db.get(UserFollow, (user.id, kind, target))
    if exists is None:
        count = (await db.execute(select(func.count()).select_from(UserFollow)
                                  .where(UserFollow.user_id == user.id))).scalar_one()
        if count >= MAX_FOLLOWS:
            raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "follow_limit", "limit": MAX_FOLLOWS})
        db.add(UserFollow(user_id=user.id, kind=kind, target=target))
        await db.commit()
    return await _follows(db, user.id)


@router.delete("/follows/{kind}/{target}", response_model=FollowsOut)
async def unfollow(kind: Literal["match", "league"], target: str, user: User = Depends(current_user),
                   db: AsyncSession = Depends(get_db)) -> FollowsOut:
    await db.execute(delete(UserFollow).where(UserFollow.user_id == user.id, UserFollow.kind == kind,
                                              UserFollow.target == target))
    await db.commit()
    return await _follows(db, user.id)


@router.get("/export")
async def export_data(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Everything stored about the account (GDPR-style access request)."""
    subs = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalars().all()
    pays = (await db.execute(select(Payment).where(Payment.user_id == user.id))).scalars().all()
    slips = (await db.execute(select(Slip).where(Slip.user_id == user.id))).scalars().all()
    logs = (await db.execute(select(AuditLog).where(AuditLog.user_id == user.id)
                             .order_by(AuditLog.created_at.desc()).limit(500))).scalars().all()
    return dict(
        account=dict(email=user.email, full_name=user.full_name, country=user.country, created_at=user.created_at,
                     email_verified_at=user.email_verified_at, age_confirmed_at=user.age_confirmed_at),
        subscriptions=[dict(plan=s.plan_code, provider=s.provider, status=s.status,
                            current_period_end=s.current_period_end) for s in subs],
        payments=[dict(provider=p.provider, amount_minor=p.amount_minor, currency=p.currency, status=p.status,
                       created_at=p.created_at) for p in pays],
        slips=[dict(kind=s.kind, target_odds=s.target_odds, combined_odds=s.combined_odds, legs=s.legs,
                    created_at=s.created_at) for s in slips],
        follows=(await _follows(db, user.id)).model_dump(),
        security_events=[dict(action=a.action, created_at=a.created_at) for a in logs],
    )


@router.delete("", response_model=Message)
async def delete_account(request: Request, response: Response, user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)) -> Message:
    """Close the account. It is disabled at once (sessions revoked, API key removed) and erased by the worker
    after ACCOUNT_RETENTION_DAYS. Payment records keep amounts for accounting but lose the link to the person."""
    erase_on = close_account(user)
    await auth.revoke_all_sessions(db, user.id)
    await audit(db, "account_closed", request, user.id, erase_after=erase_on.isoformat())
    await db.commit()
    await forget_viewer(user.id)
    auth.clear_session(response)
    days = settings.account_retention_days
    when = f"on {erase_on:%d %B %Y}" if days else "now"
    return Message(message=f"Your account is closed and you have been signed out. Your data will be erased {when}. "
                           f"Cancel any card subscription in the billing portal if it is still active.")
