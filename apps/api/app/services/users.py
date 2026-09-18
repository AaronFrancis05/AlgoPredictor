from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import AuditLog, OAuthAccount, Payment, User
from app.schemas import UserOut
from app.services.entitlements import active_plan

log = get_logger(__name__)


async def user_out(db: AsyncSession, user: User) -> UserOut:
    plan = await active_plan(db, user.id)
    google = (await db.execute(select(OAuthAccount.id).where(OAuthAccount.user_id == user.id,
                                                             OAuthAccount.provider == "google").limit(1))).first()
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, country=user.country,
                   email_verified=user.email_verified_at is not None,
                   age_confirmed=user.age_confirmed_at is not None, is_admin=user.is_admin, role=user.role,
                   plan=plan.code,
                   entitlements=plan.entitlements, has_api_key=user.api_key_digest is not None,
                   has_password=user.password_hash is not None, google_linked=google is not None,
                   created_at=user.created_at, account_retention_days=get_settings().account_retention_days)


def close_account(user: User, now: datetime | None = None) -> datetime:
    """Disable the account now and schedule its erasure. Returns when it will be erased.
    The row stays (so records exist for the retention period and support can restore it); nobody can sign in."""
    now = now or datetime.now(UTC)
    user.is_active = False
    user.deleted_at = now
    user.purge_after = now + timedelta(days=get_settings().account_retention_days)
    user.api_key_digest = None
    return user.purge_after


async def purge_closed_accounts(db: AsyncSession, now: datetime | None = None, batch: int = 200) -> int:
    """Erase accounts whose retention period has ended. Their subscriptions, slips, tokens and sign-in links are
    deleted with them (ON DELETE CASCADE); payment and audit rows keep amounts and events without the identity
    (ON DELETE SET NULL)."""
    now = now or datetime.now(UTC)
    users = (await db.execute(select(User).where(User.purge_after.is_not(None), User.purge_after <= now,
                                                 User.is_active.is_(False)).limit(batch))).scalars().all()
    ids = [u.id for u in users]
    if ids:  # explicit, so the kept records lose the identity even where foreign keys are not enforced
        await db.execute(update(Payment).where(Payment.user_id.in_(ids)).values(user_id=None))
        await db.execute(update(AuditLog).where(AuditLog.user_id.in_(ids)).values(user_id=None))
    for u in users:
        await db.delete(u)
    await db.commit()
    if users:
        log.info("closed_accounts_purged", count=len(users))
    return len(users)
