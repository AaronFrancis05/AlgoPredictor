"""Reading published picks, applying plan restrictions, and serialising them."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached
from app.core.config import get_settings
from app.models import Pick, PickResult, Plan
from app.schemas import PickOut
from app.services.products import Leg

CACHE_NS = "picks"
DISCLAIMER = ("Predictions are model probabilities, not certainties. Even the Strong tier loses about one match "
              "in four in historical testing. 18+ only. Bet only what you can afford to lose.")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _row_to_dict(p: Pick, r: PickResult | None) -> dict:
    return dict(prediction_id=p.prediction_id, model_version=p.model_version, kickoff_date=p.kickoff_date.isoformat(),
                kickoff_time=p.kickoff_time, kickoff_at=_aware(p.kickoff_at).isoformat(), league_code=p.league_code,
                home_team=p.home_team, away_team=p.away_team, p_home=p.p_home, p_draw=p.p_draw, p_away=p.p_away,
                pick=p.pick, confidence=p.confidence, tier=p.tier, odds=p.odds_used, edge=p.edge,
                value_flag=p.value_flag, is_demo=p.is_demo,
                result=r.result if r else None, correct=r.correct if r else None)


async def picks_between(db: AsyncSession, start: date, end: date) -> list[dict]:
    """Published picks with kickoff_date in [start, end], cached per range until the next ingest."""
    async def load() -> list[dict]:
        q = (select(Pick, PickResult).outerjoin(PickResult, PickResult.prediction_id == Pick.prediction_id)
             .where(Pick.kickoff_date >= start, Pick.kickoff_date <= end))
        if get_settings().is_production:  # demo rows never reach production users
            q = q.where(Pick.is_demo.is_(False))
        rows = (await db.execute(q.order_by(Pick.kickoff_at, Pick.confidence.desc()))).all()
        return [_row_to_dict(p, r) for p, r in rows]

    return await cached(CACHE_NS, f"{start}:{end}", 3600, load)


def to_leg(d: dict) -> Leg:
    return Leg(prediction_id=d["prediction_id"], kickoff_date=date.fromisoformat(d["kickoff_date"]),
               kickoff_at=datetime.fromisoformat(d["kickoff_at"]), league_code=d["league_code"],
               home_team=d["home_team"], away_team=d["away_team"], pick=d["pick"], probability=d["confidence"],
               tier=d["tier"], odds=d["odds"], value_flag=bool(d["value_flag"]))


def serialise(d: dict, plan: Plan, locked: bool = False) -> PickOut:
    s = get_settings()
    ent = plan.entitlements
    show_value = bool(ent.get("value_flags"))
    if locked:
        return PickOut(prediction_id=d["prediction_id"], kickoff_date=d["kickoff_date"],
                       kickoff_time=d["kickoff_time"], kickoff_at=d["kickoff_at"], league_code=d["league_code"],
                       home_team=d["home_team"], away_team=d["away_team"], pick=None, confidence=None,
                       tier="locked", tier_hit_rate=None, p_home=None, p_draw=None, p_away=None, fair_odds=None,
                       odds=None, edge=None, value_flag=None, locked=True, is_demo=d["is_demo"],
                       model_version=d["model_version"], result=d["result"], correct=None)
    conf = d["confidence"]
    return PickOut(prediction_id=d["prediction_id"], kickoff_date=d["kickoff_date"], kickoff_time=d["kickoff_time"],
                   kickoff_at=d["kickoff_at"], league_code=d["league_code"], home_team=d["home_team"],
                   away_team=d["away_team"], pick=d["pick"], confidence=round(conf, 3), tier=d["tier"],
                   tier_hit_rate=s.tier_hit_rates.get(d["tier"]), p_home=round(d["p_home"], 3),
                   p_draw=round(d["p_draw"], 3), p_away=round(d["p_away"], 3),
                   fair_odds=round(1 / conf, 2) if conf else None, odds=d["odds"],
                   edge=round(d["edge"], 3) if show_value and d["edge"] is not None else None,
                   value_flag=bool(d["value_flag"]) if show_value else None, locked=False, is_demo=d["is_demo"],
                   model_version=d["model_version"], result=d["result"], correct=d["correct"])


def apply_plan(day_picks: list[dict], plan: Plan, now: datetime,
               signed_in: bool = True) -> tuple[list[PickOut], int]:
    """Free plan: only the N highest-confidence picks, each revealed X hours before kick-off; others locked.
    Signed-out visitors see fixtures only: every pick is locked until they sign in."""
    if not signed_in:
        return [serialise(d, plan, locked=True) for d in day_picks], len(day_picks)
    ent = plan.entitlements
    limit = ent.get("picks_per_day")
    reveal = ent.get("reveal_hours_before_kickoff")
    if limit is None and reveal is None:
        return [serialise(d, plan) for d in day_picks], 0
    ranked = sorted(day_picks, key=lambda d: d["confidence"], reverse=True)
    free_ids = {d["prediction_id"] for d in (ranked[:limit] if limit is not None else ranked)}
    out, hidden = [], 0
    for d in day_picks:
        kickoff = datetime.fromisoformat(d["kickoff_at"])
        finished = d["result"] is not None
        revealed = reveal is None or finished or kickoff - timedelta(hours=reveal) <= now
        if d["prediction_id"] in free_ids and revealed:
            out.append(serialise(d, plan))
        else:
            out.append(serialise(d, plan, locked=True))
            hidden += 1
    return out, hidden


async def track_record(db: AsyncSession) -> dict:
    async def load() -> dict:
        base = (select(Pick, PickResult).join(PickResult, PickResult.prediction_id == Pick.prediction_id)
                .where(Pick.is_demo.is_(False)))
        rows = (await db.execute(base.order_by(Pick.kickoff_at.desc()))).all()
        n = len(rows)
        by_tier: dict[str, list] = {}
        by_month: dict[str, list] = {}
        for p, r in rows:
            by_tier.setdefault(p.tier, []).append((r.correct, p.confidence, r.rps))
            by_month.setdefault(p.kickoff_date.strftime("%Y-%m"), []).append((r.correct, r.rps))
        first = (await db.execute(select(func.min(Pick.kickoff_date)).where(Pick.is_demo.is_(False)))).scalar()
        return dict(
            graded=n,
            hit_rate=sum(r.correct for _, r in rows) / n if n else None,
            mean_rps=sum(r.rps for _, r in rows) / n if n else None,
            by_tier=[dict(tier=t, graded=len(v), hit_rate=sum(c for c, _, _ in v) / len(v),
                          avg_confidence=sum(x for _, x, _ in v) / len(v))
                     for t, v in sorted(by_tier.items())],
            by_month=[dict(month=m, graded=len(v), hit_rate=sum(c for c, _ in v) / len(v),
                           mean_rps=sum(x for _, x in v) / len(v)) for m, v in sorted(by_month.items())],
            recent=[_row_to_dict(p, r) for p, r in rows[:20]],
            live_since=first.isoformat() if first else None,
        )

    return await cached("track_record", "all", 900, load)
