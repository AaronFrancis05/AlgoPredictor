"""Account self-service: profile, API key (Elite), data export and deletion."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.core.security import hash_password, new_opaque_token, token_digest, verify_password
from app.db.session import get_db
from app.deps import current_user
from app.models import AuditLog, OAuthAccount, Payment, Slip, Subscription, User
from app.routers.auth import google_authorize_url
from app.schemas import ApiKeyOut, GoogleLinkOut, Message, PasswordSetIn, UserOut
from app.services import auth_service as auth
from app.services.audit import audit
from app.services.entitlements import require_entitlement
from app.services.users import user_out

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
        security_events=[dict(action=a.action, created_at=a.created_at) for a in logs],
    )


@router.delete("", response_model=Message)
async def delete_account(request: Request, response: Response, user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)) -> Message:
    """Delete the account. Payment records keep amounts for accounting but lose the link to the person."""
    await audit(db, "account_deleted", request, None)
    await db.delete(user)
    await db.commit()
    auth.clear_session(response)
    return Message(message="Your account has been deleted. Cancel any card subscription in the billing portal "
                           "first if it is still active.")
