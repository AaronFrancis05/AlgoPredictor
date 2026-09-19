"""In-app notifications: create them (idempotent per dedupe key), list them, mark them read, and the hourly job
that reminds people before code-granted access ends and tells them when it has ended."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Plan, Subscription, UserNotification

log = get_logger(__name__)

LIST_LIMIT = 50
KEEP_DAYS = 90             # older notifications are removed by the daily clean-up
ENDING_SOON = timedelta(days=3)
ENDED_LOOKBACK = timedelta(days=7)  # an access that ended longer ago than this is not announced any more


def _when(dt: datetime) -> str:
    dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return f"{dt:%d %B %Y, %H:%M} UTC"


async def notify_many(db: AsyncSession, items: list[dict]) -> int:
    """Add notifications (dicts with user_id, kind, title, body, link, dedupe_key). Items whose (user, dedupe_key)
    already exists are skipped, so callers may repeat themselves safely. The caller commits."""
    keyed = [i for i in items if i.get("dedupe_key")]
    existing: set[tuple[uuid.UUID, str]] = set()
    if keyed:
        rows = await db.execute(select(UserNotification.user_id, UserNotification.dedupe_key)
                                .where(UserNotification.user_id.in_({i["user_id"] for i in keyed}),
                                       UserNotification.dedupe_key.in_({i["dedupe_key"] for i in keyed})))
        existing = set(rows.all())
    added = 0
    for i in items:
        key = i.get("dedupe_key")
        if key and (i["user_id"], key) in existing:
            continue
        if key:
            existing.add((i["user_id"], key))
        db.add(UserNotification(user_id=i["user_id"], kind=i["kind"], title=i["title"][:120],
                                body=i.get("body", "")[:500], link=i.get("link"), dedupe_key=key))
        added += 1
    return added


async def notify(db: AsyncSession, user_id: uuid.UUID, kind: str, title: str, body: str = "",
                 link: str | None = None, dedupe_key: str | None = None) -> int:
    return await notify_many(db, [dict(user_id=user_id, kind=kind, title=title, body=body, link=link,
                                       dedupe_key=dedupe_key)])


async def list_for(db: AsyncSession, user_id: uuid.UUID) -> tuple[list[UserNotification], int]:
    """The newest notifications and the number still unread."""
    items = (await db.execute(select(UserNotification).where(UserNotification.user_id == user_id)
                              .order_by(UserNotification.created_at.desc(), UserNotification.id)
                              .limit(LIST_LIMIT))).scalars().all()
    unread = (await db.execute(select(func.count()).select_from(UserNotification)
                               .where(UserNotification.user_id == user_id,
                                      UserNotification.read_at.is_(None)))).scalar_one()
    return list(items), unread


async def mark_read(db: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID] | None) -> None:
    """Mark the given notifications (or all when ids is None) as read. Only the user's own rows are touched."""
    q = update(UserNotification).where(UserNotification.user_id == user_id, UserNotification.read_at.is_(None))
    if ids is not None:
        q = q.where(UserNotification.id.in_(ids))
    await db.execute(q.values(read_at=datetime.now(UTC)))


# ------------------------------------------------------------------ messages used by several places
def access_granted(user_id: uuid.UUID, sub: Subscription, plan_name: str) -> dict:
    return dict(user_id=user_id, kind="access_granted", title=f"{plan_name} plan unlocked",
                body=f"Your access code was accepted. You have the {plan_name} plan until "
                     f"{_when(sub.current_period_end)}.",
                link="/dashboard", dedupe_key=f"access_granted:{sub.id}")


def access_ended(user_id: uuid.UUID, sub_id: uuid.UUID, plan_name: str, revoked: bool) -> dict:
    why = "The access code was withdrawn" if revoked else "The access period from your code is over"
    return dict(user_id=user_id, kind="access_ended", title=f"{plan_name} access ended",
                body=f"{why}, so your {plan_name} features are no longer included. You keep any plan you pay for.",
                link="/account/plans", dedupe_key=f"access_ended:{sub_id}")


async def plan_names(db: AsyncSession) -> dict[str, str]:
    return dict((await db.execute(select(Plan.code, Plan.name))).all())


async def access_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """Hourly: warn once when code-granted access ends within ENDING_SOON, and announce once when it has ended.
    Idempotent through dedupe keys, so a missed or repeated run only delays or skips nothing."""
    now = now or datetime.now(UTC)
    names = await plan_names(db)
    base = select(Subscription).where(Subscription.provider == "access_token", Subscription.status == "active")
    ending = (await db.execute(base.where(Subscription.current_period_end > now,
                                          Subscription.current_period_end <= now + ENDING_SOON))).scalars().all()
    ended = (await db.execute(base.where(Subscription.current_period_end <= now,
                                         Subscription.current_period_end > now - ENDED_LOOKBACK))).scalars().all()
    items = []
    for s in ending:
        name = names.get(s.plan_code, s.plan_code.capitalize())
        items.append(dict(user_id=s.user_id, kind="access_ending", title=f"{name} access ends soon",
                          body=f"Your {name} access from a code ends on {_when(s.current_period_end)}. "
                               f"Choose a plan to keep these features.",
                          link="/account/plans", dedupe_key=f"access_ending:{s.id}"))
    items += [access_ended(s.user_id, s.id, names.get(s.plan_code, s.plan_code.capitalize()), revoked=False)
              for s in ended]
    added = await notify_many(db, items) if items else 0
    await db.commit()
    if added:
        log.info("access_reminders_sent", count=added)
    return added


async def purge_old(db: AsyncSession, now: datetime | None = None) -> int:
    """Remove notifications older than KEEP_DAYS, so the table stays small."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=KEEP_DAYS)
    res = await db.execute(delete(UserNotification).where(UserNotification.created_at < cutoff))
    await db.commit()
    return res.rowcount or 0
