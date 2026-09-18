"""Admin-issued access tokens: a code that grants a paid plan until the token expires.

A redemption is an ordinary Subscription (provider "access_token", current_period_end = token expiry), so
entitlements, expiry and the plan cache need no special cases. Revoking a token cancels every subscription it
created, which ends access at once.
"""
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate
from app.core.logging import get_logger
from app.core.security import token_digest
from app.models import ROLES, AccessToken, Plan, Subscription, User
from app.services.entitlements import active_plan, forget_user_plans

log = get_logger(__name__)
PROVIDER = "access_token"
# Crockford-style alphabet without I, L, O, U: easy to read aloud and type from a message
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_GROUPS, _GROUP_LEN = 4, 4  # 16 characters = 80 bits


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def normalise_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return raw[2:] if raw.startswith("AP") and len(raw) == 2 + _GROUPS * _GROUP_LEN else raw


def new_code() -> tuple[str, str]:
    """Returns (display code "AP-XXXX-XXXX-XXXX-XXXX", normalised form that is hashed)."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_GROUPS * _GROUP_LEN))
    groups = [raw[i:i + _GROUP_LEN] for i in range(0, len(raw), _GROUP_LEN)]
    return "AP-" + "-".join(groups), raw


def token_status(t: AccessToken, now: datetime, redemptions: int) -> str:
    if t.revoked_at is not None:
        return "revoked"
    if _aware(t.expires_at) <= now:
        return "expired"
    if t.max_redemptions is not None and redemptions >= t.max_redemptions:
        return "used_up"
    return "active"


async def create(db: AsyncSession, admin: User, plan_code: str, expires_at: datetime, max_redemptions: int | None,
                 note: str) -> tuple[AccessToken, str]:
    plan = await db.get(Plan, plan_code)
    if plan is None or not plan.is_active or plan.rank == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an active paid plan")
    if _aware(expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The expiry must be in the future")
    display, raw = new_code()
    token = AccessToken(code_digest=token_digest(raw), code_hint=display[:7], plan_code=plan_code,
                        expires_at=_aware(expires_at), max_redemptions=max_redemptions, note=note.strip(),
                        created_by=admin.id)
    db.add(token)
    await db.flush()
    return token, display


async def redemption_counts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = await db.execute(select(Subscription.access_token_id, func.count())
                            .where(Subscription.access_token_id.in_(ids)).group_by(Subscription.access_token_id))
    return dict(rows.all())


async def redeemers(db: AsyncSession, token_id: uuid.UUID, limit: int = 50) -> list[dict]:
    rows = await db.execute(select(User.email, Subscription.created_at, Subscription.status)
                            .join(User, User.id == Subscription.user_id)
                            .where(Subscription.access_token_id == token_id)
                            .order_by(Subscription.created_at.desc()).limit(limit))
    return [dict(email=e, redeemed_at=at, status=s) for e, at, s in rows.all()]


async def revoke(db: AsyncSession, token_id: uuid.UUID) -> AccessToken:
    token = await db.get(AccessToken, token_id)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    now = datetime.now(UTC)
    token.revoked_at = token.revoked_at or now
    await db.execute(update(Subscription).where(Subscription.access_token_id == token_id,
                                                Subscription.status != "canceled")
                     .values(status="canceled", current_period_end=now, updated_at=now))
    return token


async def redeem(db: AsyncSession, user: User, code: str) -> Subscription:
    """Give `user` the token's plan until the token expires. Every failure reads the same, so the endpoint
    cannot be used to learn which codes exist."""
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "This code is not valid, has expired or has been used up")
    raw = normalise_code(code)
    if len(raw) != _GROUPS * _GROUP_LEN:
        raise invalid
    token = (await db.execute(select(AccessToken).where(AccessToken.code_digest == token_digest(raw))
                              .with_for_update())).scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None:
        raise invalid
    used = (await redemption_counts(db, [token.id])).get(token.id, 0)
    if token_status(token, now, used) != "active":
        raise invalid
    mine = (await db.execute(select(Subscription).where(Subscription.access_token_id == token.id,
                                                        Subscription.user_id == user.id))).scalar_one_or_none()
    if mine is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already used this code")
    # A code must add something: redeeming a plan the user already has (or a lower one) would use up one of the
    # code's redemptions for nothing. Checked after validity, so this reveals nothing about unknown codes.
    current = await active_plan(db, user.id)
    granted = await db.get(Plan, token.plan_code)
    if granted is None or current.rank >= granted.rank:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "plan_already_covered", "plan": current.code,
                                    "token_plan": token.plan_code})
    sub = Subscription(user_id=user.id, plan_code=token.plan_code, provider=PROVIDER, status="active",
                       current_period_end=_aware(token.expires_at), access_token_id=token.id)
    db.add(sub)
    return sub


async def set_role(db: AsyncSession, email: str, role: str) -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    user = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    if user is None:
        raise LookupError(f"no account with email {email}")
    user.role = role
    return user


async def after_change() -> None:
    """Plans derived from tokens or roles changed: drop cached plans (and viewers, which carry the role) so it
    shows at once. Raises if the viewer cache cannot be invalidated, so a role change is not reported as done
    while other instances may still serve the old role (local copies are dropped regardless)."""
    await forget_user_plans()
    await invalidate("viewer")
