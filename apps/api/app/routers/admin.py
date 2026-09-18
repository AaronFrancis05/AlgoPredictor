"""Minimal admin: platform stats and failed webhooks (read-only)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import admin_user
from app.models import Pick, PickResult, Subscription, User, WebhookEvent

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)) -> dict:
    count = lambda q: db.execute(select(func.count()).select_from(q))  # noqa: E731
    return dict(
        users=(await count(User)).scalar_one(),
        active_subscriptions={plan: n for plan, n in (await db.execute(
            select(Subscription.plan_code, func.count()).where(Subscription.status.in_(("active", "trialing")))
            .group_by(Subscription.plan_code))).all()},
        picks=(await count(Pick)).scalar_one(),
        graded=(await count(PickResult)).scalar_one(),
        failed_webhooks=(await db.execute(select(func.count()).select_from(WebhookEvent)
                                          .where(WebhookEvent.error.is_not(None)))).scalar_one(),
    )


@router.get("/webhooks/failed")
async def failed_webhooks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(WebhookEvent).where(WebhookEvent.error.is_not(None))
                             .order_by(WebhookEvent.received_at.desc()).limit(100))).scalars().all()
    return [dict(provider=r.provider, event_id=r.event_id, type=r.event_type, received_at=r.received_at,
                 error=r.error) for r in rows]
