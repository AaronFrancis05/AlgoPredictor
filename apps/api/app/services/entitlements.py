"""Plan entitlements. Defaults are seeded into the `plans` table and can be edited there."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Plan, Subscription, User

ACTIVE_STATUSES = ("active", "trialing")

DEFAULT_PLANS = [
    dict(code="free", name="Free", rank=0,
         description="A taste of the model: three picks a day, revealed two hours before kick-off.",
         entitlements=dict(picks_per_day=3, reveal_hours_before_kickoff=2, top10=False, slip_builder=False,
                           slips_per_day=0, jackpot=False, value_flags=False, api_access=False)),
    dict(code="pro", name="Pro", rank=1,
         description="Every daily pick, the daily top 10 and the target-odds slip builder.",
         entitlements=dict(picks_per_day=None, reveal_hours_before_kickoff=None, top10=True, slip_builder=True,
                           slips_per_day=5, jackpot=False, value_flags=False, api_access=False)),
    dict(code="elite", name="Elite", rank=2,
         description="Everything in Pro plus the weekly jackpot, VALUE flags, unlimited slips and API access.",
         entitlements=dict(picks_per_day=None, reveal_hours_before_kickoff=None, top10=True, slip_builder=True,
                           slips_per_day=None, jackpot=True, value_flags=True, api_access=True)),
]

# (plan, currency, interval, amount in ISO-4217 minor units) - editable in the prices table / admin.
# UGX and RWF have no minor unit (amount = whole shillings/francs); every other currency here uses cents.
ZERO_DECIMAL_CURRENCIES = {"UGX", "RWF"}
DEFAULT_PRICES = [
    ("pro", "USD", "month", 999), ("pro", "USD", "year", 9900),          # $9.99 / $99
    ("elite", "USD", "month", 2499), ("elite", "USD", "year", 24900),    # $24.99 / $249
    ("pro", "EUR", "month", 949), ("elite", "EUR", "month", 2349),       # EUR 9.49 / 23.49
    ("pro", "GBP", "month", 849), ("elite", "GBP", "month", 1999),       # GBP 8.49 / 19.99
    ("pro", "UGX", "month", 37000), ("elite", "UGX", "month", 92000),    # UGX 37,000 / 92,000
    ("pro", "KES", "month", 130000), ("elite", "KES", "month", 320000),  # KES 1,300 / 3,200
    ("pro", "NGN", "month", 1500000), ("elite", "NGN", "month", 3750000),  # NGN 15,000 / 37,500
]


def major_units(amount_minor: int, currency: str) -> float:
    return amount_minor if currency in ZERO_DECIMAL_CURRENCIES else amount_minor / 100


async def active_plan(db: AsyncSession, user_id: UUID | None) -> Plan:
    if user_id is not None:
        now = datetime.now(UTC)
        rows = (await db.execute(
            select(Plan).join(Subscription, Subscription.plan_code == Plan.code)
            .where(Subscription.user_id == user_id, Subscription.status.in_(ACTIVE_STATUSES))
            .where((Subscription.current_period_end.is_(None)) | (Subscription.current_period_end > now))
            .order_by(Plan.rank.desc()))).scalars().first()
        if rows is not None:
            return rows
    free = await db.get(Plan, "free")
    if free is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Plans are not configured")
    return free


def allows(plan: Plan, feature: str) -> bool:
    return bool(plan.entitlements.get(feature))


def require_entitlement(feature: str):
    from app.deps import current_user  # local import to avoid a cycle

    async def dependency(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Plan:
        plan = await active_plan(db, user.id)
        if not allows(plan, feature):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail={"code": "upgrade_required", "feature": feature, "plan": plan.code})
        return plan

    return dependency
