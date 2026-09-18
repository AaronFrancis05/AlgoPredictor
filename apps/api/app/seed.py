"""Seed plans and prices (idempotent).  python -m app.seed [--demo-picks]

--demo-picks inserts clearly labelled DEMO picks (is_demo=True, model_version="demo") built from random
probabilities, so the UI can be shown before live predictions exist. They are never presented as real
predictions and are excluded from the track record. Do not use in production.
"""
import argparse
import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Pick, Plan, Price
from app.services.entitlements import DEFAULT_PLANS, DEFAULT_PRICES
from app.services.ingest import after_publish, kickoff_utc

DEMO_TEAMS = [("E0", "Arsenal", "Everton"), ("E0", "Liverpool", "Fulham"), ("SP1", "Barcelona", "Getafe"),
              ("I1", "Inter", "Lecce"), ("D1", "Bayern Munich", "Mainz"), ("F1", "Paris SG", "Nantes"),
              ("N1", "PSV", "Heracles"), ("P1", "Benfica", "Arouca"), ("E1", "Leeds", "Hull"),
              ("SP1", "Sevilla", "Osasuna"), ("I1", "Napoli", "Torino"), ("D1", "Dortmund", "Augsburg"),
              ("F1", "Lyon", "Metz"), ("T1", "Galatasaray", "Rizespor"), ("B1", "Club Brugge", "Mechelen")]


async def seed_plans() -> None:
    async with get_sessionmaker()() as db:
        for p in DEFAULT_PLANS:
            row = await db.get(Plan, p["code"])
            if row is None:
                db.add(Plan(**p))
        await db.flush()
        for plan, cur, interval, amount in DEFAULT_PRICES:
            exists = (await db.execute(select(Price).where(Price.plan_code == plan, Price.currency == cur,
                                                           Price.interval == interval))).scalar_one_or_none()
            if exists is None:
                db.add(Price(plan_code=plan, currency=cur, interval=interval, amount_minor=amount))
        await db.commit()
    print("plans and prices seeded (set stripe_price_id / flutterwave_plan_id per price before selling)")


async def seed_demo_picks(days: int = 7) -> None:
    if get_settings().is_production:
        raise SystemExit("Refusing to seed demo picks in production")
    rng = random.Random(42)  # noqa: S311 - deterministic demo data, not security-related
    async with get_sessionmaker()() as db:
        n = 0
        for d in range(days):
            day = datetime.now(UTC).date() + timedelta(days=d)
            for i, (lg, home, away) in enumerate(rng.sample(DEMO_TEAMS, 8)):
                pid = f"demo-{day:%Y%m%d}-{i}"
                if await db.get(Pick, pid):
                    continue
                ph = rng.uniform(0.25, 0.8)
                pd_ = rng.uniform(0.15, min(0.32, 1 - ph - 0.05))
                pa = 1 - ph - pd_
                probs = {"home": ph, "draw": pd_, "away": pa}
                pick = max(probs, key=probs.get)
                conf = probs[pick]
                tier = "Strong" if conf >= 0.65 else "Medium" if conf >= 0.5 else "Lean"
                odds = round(max(1.05, (1 / conf) * rng.uniform(0.88, 1.08)), 2)
                hhmm = f"{rng.choice([12, 14, 15, 17, 19, 20]):02d}:{rng.choice(['00', '30'])}"
                db.add(Pick(prediction_id=pid, model_version="demo", made_at=datetime.now(UTC),
                            kickoff_date=day, kickoff_time=hhmm, kickoff_at=kickoff_utc(day, hhmm), league_code=lg,
                            home_team=home, away_team=away, p_home=round(ph, 4), p_draw=round(pd_, 4),
                            p_away=round(pa, 4), pick=pick, confidence=round(conf, 4), tier=tier, odds_used=odds,
                            odds_source="demo", edge=round(conf * odds - 1, 4), value_flag=conf * odds - 1 > 0.05,
                            flags="DEMO DATA", is_demo=True))
                n += 1
        await db.commit()
    await after_publish()
    print(f"inserted {n} DEMO picks (is_demo=True) for {date.today()} + {days - 1} days")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-picks", action="store_true")
    args = ap.parse_args()
    asyncio.run(seed_plans())
    if args.demo_picks:
        asyncio.run(seed_demo_picks())


if __name__ == "__main__":
    main()
