"""Background worker (arq): retries failed webhook events and warms caches.

  arq app.workers.worker.WorkerSettings
"""
from datetime import UTC, datetime, timedelta

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_sessionmaker
from app.models import WebhookEvent
from app.services import billing, picks_service

log = get_logger("worker")


async def retry_failed_webhooks(ctx) -> int:
    """Re-process events stored but not yet applied (e.g. provider API was down)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(WebhookEvent.provider, WebhookEvent.event_id)
                                 .where(WebhookEvent.processed_at.is_(None), WebhookEvent.received_at < cutoff)
                                 .limit(100))).all()
        for provider, event_id in rows:
            await billing.process_event(db, provider, event_id)
    if rows:
        log.info("webhooks_retried", count=len(rows))
    return len(rows)


async def warm_cache(ctx) -> None:
    today = datetime.now(UTC).date()
    async with get_sessionmaker()() as db:
        await picks_service.picks_between(db, today, today)
        await picks_service.picks_between(db, today, today + timedelta(days=3))
        await picks_service.track_record(db)


async def startup(ctx) -> None:
    configure_logging(get_settings().log_level)


def _redis_settings() -> RedisSettings:
    """rediss:// (Upstash) turns on TLS; retry the connection so a dropped idle socket does not kill the worker."""
    rs = RedisSettings.from_dsn(get_settings().redis_url)
    rs.conn_timeout, rs.conn_retries, rs.conn_retry_delay = 10, 10, 2
    rs.retry_on_timeout = True
    return rs


class WorkerSettings:
    redis_settings = _redis_settings()
    # Nothing enqueues ad-hoc jobs (only the crons below), so polling slowly loses nothing; each poll is one
    # billed Redis command on Upstash. Crons fire at most poll_delay seconds late.
    poll_delay = get_settings().worker_poll_delay_seconds
    functions = [retry_failed_webhooks, warm_cache]
    cron_jobs = [cron(retry_failed_webhooks, minute=set(range(0, 60, 5))),
                 cron(warm_cache, minute=set(range(0, 60, 10)))]
    on_startup = startup
