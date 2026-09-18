"""Idempotent ingest of picks and graded results from the ML pipeline. Existing rows are never changed:
logged predictions are permanent (parent project rule)."""
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate
from app.core.config import get_settings
from app.core.events import publish
from app.core.logging import get_logger
from app.models import Pick, PickResult
from app.schemas import IngestPick, IngestResult

log = get_logger(__name__)
UK = ZoneInfo("Europe/London")


def kickoff_utc(day: date, hhmm: str) -> datetime:
    """football-data kick-off times are UK local; a missing time counts as 00:00 (conservative)."""
    try:
        t = time.fromisoformat(hhmm) if hhmm else time(0, 0)
    except ValueError:
        t = time(0, 0)
    return datetime.combine(day, t, tzinfo=UK).astimezone(UTC)


def _flag(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().upper() == "VALUE")


async def ingest_picks(db: AsyncSession, picks: list[IngestPick]) -> tuple[int, int]:
    ids = [p.prediction_id for p in picks]
    existing = set((await db.execute(select(Pick.prediction_id).where(Pick.prediction_id.in_(ids)))).scalars())
    new = 0
    seen: set[str] = set()
    for p in picks:
        if p.prediction_id in existing or p.prediction_id in seen:
            continue
        seen.add(p.prediction_id)
        db.add(Pick(prediction_id=p.prediction_id, model_version=p.model_version, made_at=p.made_at,
                    kickoff_date=p.date, kickoff_time=p.time or "", kickoff_at=kickoff_utc(p.date, p.time or ""),
                    league_code=p.league_code, home_team=p.home_team, away_team=p.away_team, p_home=p.p_home,
                    p_draw=p.p_draw, p_away=p.p_away, pick=p.pick, confidence=p.confidence, tier=p.tier,
                    odds_used=p.odds_used, odds_source=p.odds_source, edge=p.edge, value_flag=_flag(p.value_flag),
                    flags=p.flags or "", is_demo=p.is_demo))
        new += 1
    await db.commit()
    if new:
        await after_publish()
    return new, len(picks) - new


async def ingest_results(db: AsyncSession, results: list[IngestResult]) -> tuple[int, int]:
    ids = [r.prediction_id for r in results]
    known = set((await db.execute(select(Pick.prediction_id).where(Pick.prediction_id.in_(ids)))).scalars())
    graded = set((await db.execute(select(PickResult.prediction_id)
                                   .where(PickResult.prediction_id.in_(ids)))).scalars())
    new = 0
    for r in results:
        if r.prediction_id not in known or r.prediction_id in graded:
            continue
        graded.add(r.prediction_id)
        db.add(PickResult(prediction_id=r.prediction_id, result=r.result, correct=r.correct, rps=r.rps,
                          profit=r.profit))
        new += 1
    await db.commit()
    if new:
        await after_publish()
    return new, len(results) - new


async def after_publish() -> None:
    await invalidate("picks")
    await invalidate("track_record")
    await publish("picks")  # open pages refetch now
    s = get_settings()
    if not s.web_revalidate_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(s.web_revalidate_url,
                              headers={"x-revalidate-secret": s.web_revalidate_secret.get_secret_value()},
                              json={"tags": ["picks", "track-record"]})
    except httpx.HTTPError as e:
        log.warning("web_revalidate_failed", error=str(e))
