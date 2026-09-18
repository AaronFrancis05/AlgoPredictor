"""Prediction products: daily picks, daily top 10, target-odds slips, weekly jackpot, track record."""
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.deps import optional_user, verified_adult
from app.models import Plan, Slip, User
from app.schemas import JackpotDayOut, JackpotOut, PicksDayOut, SlipIn, SlipOut, TrackRecordOut
from app.services import picks_service as ps
from app.services import products
from app.services.entitlements import active_plan, require_entitlement

settings = get_settings()
router = APIRouter(tags=["predictions"])
product_limit = rate_limit("products", settings.rate_limit_products)
MAX_RANGE_DAYS = 14


def _today() -> date:
    return datetime.now(UTC).date()


@router.get("/picks", response_model=PicksDayOut, dependencies=[Depends(product_limit)])
async def picks_for_day(response: Response, day: date | None = Query(default=None, alias="date"),
                        user: User | None = Depends(optional_user), db: AsyncSession = Depends(get_db)) -> PicksDayOut:
    """Picks for one day. Signed-out visitors see every pick locked; the Free plan sees its free allocation and
    paid plans see everything their entitlements allow."""
    day = day or _today()
    if user is not None and (user.email_verified_at is None or user.age_confirmed_at is None):
        user = None  # unverified accounts get the anonymous view
    plan = await active_plan(db, user.id if user else None)
    rows = await ps.picks_between(db, day, day)
    items, hidden = ps.apply_plan(rows, plan, datetime.now(UTC), signed_in=user is not None)
    response.headers["Cache-Control"] = "private, max-age=60" if user else "public, max-age=60"
    return PicksDayOut(date=day, plan=plan.code, picks=items, total_published=len(rows), hidden_count=hidden,
                       tier_hit_rates=settings.tier_hit_rates, tier_hit_rates_source=settings.tier_hit_rates_label,
                       disclaimer=ps.DISCLAIMER)


@router.get("/picks/top", response_model=PicksDayOut)
async def top_picks(day: date | None = Query(default=None, alias="date"), n: int = Query(default=10, ge=1, le=10),
                    user: User = Depends(verified_adult), plan: Plan = Depends(require_entitlement("top10")),
                    _rl: None = Depends(product_limit), db: AsyncSession = Depends(get_db)) -> PicksDayOut:
    """The day's n highest-confidence single picks (Pro and Elite)."""
    day = day or _today()
    rows = await ps.picks_between(db, day, day)
    by_id = {r["prediction_id"]: r for r in rows}
    top = products.top_n([ps.to_leg(r) for r in rows], day, n)
    return PicksDayOut(date=day, plan=plan.code, picks=[ps.serialise(by_id[x.prediction_id], plan) for x in top],
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
    res = products.build_target_slip([ps.to_leg(r) for r in rows], body.target_odds, tolerance=body.tolerance,
                                     min_legs=body.min_legs, max_legs=body.max_legs, prefer_value=prefer_value,
                                     now=datetime.now(UTC))
    if res.found:
        db.add(Slip(user_id=user.id, kind="target_odds", target_odds=body.target_odds, combined_odds=res.combined_odds,
                    combined_probability=res.combined_probability, legs=[x.prediction_id for x in res.legs]))
        await db.commit()
    elif remaining is not None:
        remaining += 1  # a failed search does not use the quota
    return SlipOut(found=res.found, target_odds=body.target_odds, combined_odds=res.combined_odds,
                   combined_probability=res.combined_probability, expected_value=res.expected_value,
                   legs=[ps.serialise(by_id[x.prediction_id], plan) for x in res.legs], message=res.message,
                   remaining_today=remaining)


@router.get("/jackpot", response_model=JackpotOut)
async def jackpot(week_of: date | None = None, user: User = Depends(verified_adult),
                  plan: Plan = Depends(require_entitlement("jackpot")), _rl: None = Depends(product_limit),
                  db: AsyncSession = Depends(get_db)) -> JackpotOut:
    """Weekly jackpot: the two highest-confidence picks for each day of the ISO week (Elite)."""
    days = products.iso_week_days(week_of or _today())
    rows = await ps.picks_between(db, days[0], days[-1])
    by_id = {r["prediction_id"]: r for r in rows}
    j = products.weekly_jackpot([ps.to_leg(r) for r in rows], days[0])
    return JackpotOut(week_start=j["week_start"], complete=j["complete"],
                      week_combined_probability=j["week_combined_probability"], note=j["note"],
                      days=[JackpotDayOut(date=d["date"], complete=d["complete"],
                                          combined_probability=d["combined_probability"],
                                          legs=[ps.serialise(by_id[x.prediction_id], plan) for x in d["legs"]])
                            for d in j["days"]])


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
