from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OAuthAccount, User
from app.schemas import UserOut
from app.services.entitlements import active_plan


async def user_out(db: AsyncSession, user: User) -> UserOut:
    plan = await active_plan(db, user.id)
    google = (await db.execute(select(OAuthAccount.id).where(OAuthAccount.user_id == user.id,
                                                             OAuthAccount.provider == "google").limit(1))).first()
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, country=user.country,
                   email_verified=user.email_verified_at is not None,
                   age_confirmed=user.age_confirmed_at is not None, is_admin=user.is_admin, plan=plan.code,
                   entitlements=plan.entitlements, has_api_key=user.api_key_digest is not None,
                   has_password=user.password_hash is not None, google_linked=google is not None)
