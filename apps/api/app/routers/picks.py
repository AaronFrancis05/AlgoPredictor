"""Prediction products: daily picks, live matches, history, daily top 10, target-odds slips, weekly jackpot,
track record. Every pick carries its match phase (upcoming / live / finished ...) so clients can move a match from
the day's list to Live at kick-off and to History after the final whistle."""
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.deps import optional_user, verified_adult
from app.models import Plan, Slip, User
from app.schemas import (
    HistoryOut,
    HistorySummary,
    JackpotDayOut,
    JackpotOut,
    LivePicksOut,
    PickOut,
    PicksDayOut,
    SlipIn,
    SlipOut,
    TrackRecordOut,
)
from app.services import picks_service as ps
from app.services import products
from app.services.entitlements import active_plan, require_entitlement

settings = get_settings()
router = APIRouter(tags=["predictions"])
product_limit = rate_limit("products", settings.rate_limit_products)
MAX_RANGE_DAYS = 14
MAX_HISTORY_DAYS = 92
HISTORY_PHASES = {"finished", "awaiting_result", "postponed", "cancelled", "abandoned"}
VOID_PHASES = {"postponed", "cancelled", "abandoned"}


def _today() -> date:
    return datetime.now(UTC).date()


async def _viewer_plan(db: AsyncSession, user: User | None) -> tuple[User | None, Plan]:
    if user is not None and (user.email_verified_at is None or user.age_confirmed_at is None):
        user = None  # unverified accounts get the anonymous view
    return user, await active_plan(db, user.id if user else None)


@router.get("/picks", response_model=PicksDayOut, dependencies=[Depends(product_limit)])
async def picks_for_day(response: Response, day: date | None = Query(default=None, alias="date"),
                        user: User | None = Depends(optional_user), db: AsyncSession = Depends(get_db)) -> PicksDayOut:
    """Picks for one day. Signed-out visitors see every pick locked; the Free plan sees its free allocation and
    paid plans see everything their entitlements allow."""
    day = day or _today()
    now = datetime.now(UTC)
    user, plan = await _viewer_plan(db, user)
    rows = await ps.picks_between(db, day, day)
    items, hidden = ps.apply_plan(rows, plan, now, signed_in=user is not None)
    await ps.with_status(db, items, now)
    response.headers["Cache-Control"] = "private, max-age=30" if user else "public, max-age=30"
    return PicksDayOut(date=day, plan=plan.code, picks=items, total_published=len(rows), hidden_count=hidden,
                       tier_hit_rates=settings.tier_hit_rates, tier_hit_rates_source=settings.tier_hit_rates_label,
                       disclaimer=ps.DISCLAIMER)


@router.get("/picks/live", response_model=LivePicksOut, dependencies=[Depends(product_limit)])
async def live_picks(response: Response, user: User | None = Depends(optional_user),
                     db: AsyncSession = Depends(get_db)) -> LivePicksOut:
    """Matches in play now, with the live score when the feed has it. Picks follow the same plan rules as /picks
    (a locked pick stays locked until the result is in)."""
    now = datetime.now(UTC)
    user, plan = await _viewer_plan(db, user)
    today = now.date()
    rows = [r for r in await ps.picks_between(db, today - timedelta(days=1), today + timedelta(days=1))
            if datetime.fromisoformat(r["kickoff_at"]) <= now + timedelta(minutes=5)]
    items = await ps.with_status(db, ps.apply_plan_by_day(rows, plan, now, signed_in=user is not None), now)
    live = sorted((p for p in items if p.phase == "live"), key=lambda p: (p.kickoff_at, p.home_team))
    response.headers["Cache-Control"] = "private, max-age=15" if user else "public, max-age=15"
    return LivePicksOut(plan=plan.code, picks=live, feed=bool(settings.api_football_key.get_secret_value()),
                        disclaimer=ps.DISCLAIMER)


def _summary(picks: list[PickOut]) -> tuple[HistorySummary, list[dict]]:
    won = sum(p.outcome == "won" for p in picks)
    lost = sum(p.outcome == "lost" for p in picks)
    void = sum(p.phase in VOID_PHASES for p in picks)
    tiers = []
    for t in ("Strong", "Medium", "Lean"):
        w = sum(p.outcome == "won" and p.tier == t for p in picks)
        n = w + sum(p.outcome == "lost" and p.tier == t for p in picks)
        tiers.append(dict(tier=t, settled=n, won=w, hit_rate=w / n if n else None))
    return HistorySummary(matches=len(picks), won=won, lost=lost, void=void,
                          pending=len(picks) - won - lost - void,
                          hit_rate=won / (won + lost) if won + lost else None,
                          provisional=sum(p.outcome is not None and not p.outcome_official for p in picks)), tiers


@router.get("/picks/history", response_model=HistoryOut)
async def history(response: Response, date_from: date | None = None, date_to: date | None = None,
                  league: str | None = Query(default=None, max_length=8),
                  tier: Literal["Strong", "Medium", "Lean"] | None = None,
                  outcome: Literal["won", "lost", "pending"] | None = None,
                  page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=10, le=200),
                  user: User = Depends(verified_adult), _rl: None = Depends(product_limit),
                  db: AsyncSession = Depends(get_db)) -> HistoryOut:
    """Matches that have been played (or called off), newest first. Every pick is shown: the match is over."""
    now = datetime.now(UTC)
    end = date_to or now.date()
    start = date_from or end - timedelta(days=13)
    if end < start or (end - start).days > MAX_HISTORY_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Date range must be 0-{MAX_HISTORY_DAYS} days")
    plan = await active_plan(db, user.id)
    rows = [r for r in await ps.picks_between(db, start, end)
            if datetime.fromisoformat(r["kickoff_at"]) <= now]
    items = await ps.with_status(db, [ps.serialise(r, plan) for r in rows], now)
    done = [p for p in items if p.phase in HISTORY_PHASES]
    leagues = sorted({p.league_code for p in done})
    done = [p for p in done if (not league or p.league_code == league) and (not tier or p.tier == tier)]
    summary, by_tier = _summary(done)
    if outcome == "pending":
        done = [p for p in done if p.outcome is None and p.phase not in VOID_PHASES]
    elif outcome:
        done = [p for p in done if p.outcome == outcome]
    done.sort(key=lambda p: (p.kickoff_at, p.home_team), reverse=True)
    response.headers["Cache-Control"] = "private, max-age=60"
    return HistoryOut(date_from=start, date_to=end, page=page, page_size=page_size, total=len(done),
                      summary=summary, by_tier=by_tier, leagues=leagues,
                      picks=done[(page - 1) * page_size: page * page_size], disclaimer=ps.DISCLAIMER)


@router.get("/picks/top", response_model=PicksDayOut)
async def top_picks(day: date | None = Query(default=None, alias="date"), n: int = Query(default=10, ge=1, le=10),
                    user: User = Depends(verified_adult), plan: Plan = Depends(require_entitlement("top10")),
                    _rl: None = Depends(product_limit), db: AsyncSession = Depends(get_db)) -> PicksDayOut:
    """The day's n highest-confidence single picks (Pro and Elite)."""
    day = day or _today()
    rows = await ps.picks_between(db, day, day)
    by_id = {r["prediction_id"]: r for r in rows}
    top = products.top_n([ps.to_leg(r) for r in rows], day, n)
    items = await ps.with_status(db, [ps.serialise(by_id[x.prediction_id], plan) for x in top], datetime.now(UTC))
    return PicksDayOut(date=day, plan=plan.code, picks=items,
                       total_published=len(rows), hidden_count=0, tier_hit_rates=settings.tier_hit_rates,
                       tier_hit_rates_source=settings.tier_hit_rates_label, disclaimer=ps.DISCLAIMER)


@router.post("/slips", response_model=SlipOut)
async def build_slip(body: SlipIn, user: User = Depends(verified_adult),
                     plan: Plan = Depends(require_entitlement("slip_builder")), _rl: None = Depends(product_limit),
                     db: AsyncSession = Depends(get_db)) -> SlipOut:
    """Build a slip whose combined odds land near the user's target (Pro: 5/day, Elite: unlimited)."""
    start = body.date_from or _today()
    end = body.date_to or start + timedelta(days=3)
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Date range must be 0-{MAX_RANGE_DAYS} days")
    quota = plan.entitlements.get("slips_per_day")
    remaining = None
    if quota is not None:
        day_start = datetime.combine(_today(), datetime.min.time(), tzinfo=UTC)
        used = (await db.execute(select(func.count()).select_from(Slip).where(
            Slip.user_id == user.id, Slip.kind == "target_odds", Slip.created_at >= day_start))).scalar_one()
        if used >= quota:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                detail={"code": "slip_quota", "limit": quota, "plan": plan.code})
        remaining = quota - used - 1
    rows = await ps.picks_between(db, start, end)
    by_id = {r["prediction_id"]: r for r in rows}
    prefer_value = body.prefer_value and bool(plan.entitlements.get("value_flags"))
    now = datetime.now(UTC)
    res = products.build_target_slip([ps.to_leg(r) for r in rows], body.target_odds, tolerance=body.tolerance,
                                     min_legs=body.min_legs, max_legs=body.max_legs, prefer_value=prefer_value,
                                     now=now)
    if res.found:
        db.add(Slip(user_id=user.id, kind="target_odds", target_odds=body.target_odds, combined_odds=res.combined_odds,
                    combined_probability=res.combined_probability, legs=[x.prediction_id for x in res.legs]))
        await db.commit()
    elif remaining is not None:
        remaining += 1  # a failed search does not use the quota
    legs = await ps.with_status(db, [ps.serialise(by_id[x.prediction_id], plan) for x in res.legs], now)
    return SlipOut(found=res.found, target_odds=body.target_odds, combined_odds=res.combined_odds,
                   combined_probability=res.combined_probability, expected_value=res.expected_value,
                   legs=legs, message=res.message, remaining_today=remaining)


@router.get("/jackpot", response_model=JackpotOut)
async def jackpot(week_of: date | None = None, user: User = Depends(verified_adult),
                  plan: Plan = Depends(require_entitlement("jackpot")), _rl: None = Depends(product_limit),
                  db: AsyncSession = Depends(get_db)) -> JackpotOut:
    """Weekly jackpot: the two highest-confidence picks for each day of the ISO week (Elite). Legs keep their
    place once played, with the live score or result, so the week can be followed to the end."""
    days = products.iso_week_days(week_of or _today())
    rows = await ps.picks_between(db, days[0], days[-1])
    by_id = {r["prediction_id"]: r for r in rows}
    j = products.weekly_jackpot([ps.to_leg(r) for r in rows], days[0])
    now = datetime.now(UTC)
    out_days = []
    for d in j["days"]:
        legs = await ps.with_status(db, [ps.serialise(by_id[x.prediction_id], plan) for x in d["legs"]], now)
        out_days.append(JackpotDayOut(date=d["date"], complete=d["complete"],
                                      combined_probability=d["combined_probability"], legs=legs))
    return JackpotOut(week_start=j["week_start"], complete=j["complete"],
                      week_combined_probability=j["week_combined_probability"], note=j["note"], days=out_days)


@router.get("/track-record", response_model=TrackRecordOut)
async def track_record(response: Response, db: AsyncSession = Depends(get_db)) -> TrackRecordOut:
    """Public, graded history of live predictions plus the historical hit rate per tier. Internal model
    metrics (RPS, model name, test method) are deliberately left out of this public payload."""
    tr = await ps.track_record(db)
    # finished matches are public in full; VALUE flags stay a paid feature
    public_view = Plan(code="public", name="", rank=0, entitlements={"value_flags": False})
    response.headers["Cache-Control"] = "public, max-age=300"
    return TrackRecordOut(
        graded=tr["graded"], hit_rate=tr["hit_rate"], by_tier=tr["by_tier"],
        by_month=[{k: v for k, v in m.items() if k != "mean_rps"} for m in tr["by_month"]],
        recent=[ps.serialise(r, public_view) for r in tr["recent"]],
        live_since=tr["live_since"],
        backtest=dict(matches=settings.backtest_matches, tier_hit_rates=settings.tier_hit_rates,
                      note="Results on past matches. Past performance does not guarantee future results."))
