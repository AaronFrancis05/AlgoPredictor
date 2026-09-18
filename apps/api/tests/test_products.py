"""Unit tests for the pure product logic (no DB)."""
import math
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.products import Leg, build_target_slip, iso_week_days, top_n, weekly_jackpot

NOW = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
DAY = date(2026, 9, 19)


def leg(i: int, odds: float | None, prob: float, day: date = DAY, value: bool = False, home: str | None = None) -> Leg:
    return Leg(prediction_id=f"p{i}", kickoff_date=day, kickoff_at=datetime.combine(day, datetime.min.time(),
                                                                                     tzinfo=UTC) + timedelta(hours=15),
               league_code="E0", home_team=home or f"H{i}", away_team=f"A{i}", pick="home", probability=prob,
               tier="Medium", odds=odds, value_flag=value)


def test_slip_hits_target_with_one_leg_per_match_and_odds_band():
    legs = [leg(i, o, p) for i, (o, p) in enumerate([(1.5, .66), (1.8, .55), (2.2, .45), (2.0, .5), (1.3, .77),
                                                     (3.1, .30), (1.15, .85), (2.4, .41)])]
    res = build_target_slip(legs, 5.0, now=NOW)
    assert res.found
    assert 5.0 * 0.85 <= res.combined_odds <= 5.0 * 1.15
    assert all(1.20 <= x.odds <= 2.50 for x in res.legs)
    assert len({x.match_key for x in res.legs}) == len(res.legs)
    assert math.isclose(res.combined_probability, math.prod(x.probability for x in res.legs), rel_tol=1e-3)
    assert "independent" in res.message


def test_slip_maximises_probability():
    legs = [leg(0, 2.0, .50), leg(1, 2.0, .52), leg(2, 2.0, .40), leg(3, 2.0, .45)]
    res = build_target_slip(legs, 4.0, now=NOW, max_legs=2)
    assert {x.prediction_id for x in res.legs} == {"p0", "p1"}


def test_slip_not_padded_when_unreachable():
    legs = [leg(i, 1.25, .8) for i in range(3)]
    res = build_target_slip(legs, 50.0, now=NOW)
    assert not res.found and res.legs == [] and "not padded" in res.message


def test_slip_skips_started_matches_and_duplicate_matches():
    started = leg(9, 2.0, .6, day=date(2026, 9, 17))
    dup_a, dup_b = leg(1, 2.0, .6, home="Same"), leg(2, 2.1, .5, home="Same")
    object.__setattr__(dup_b, "away_team", dup_a.away_team)
    res = build_target_slip([started, dup_a, dup_b, leg(3, 2.0, .55)], 4.0, now=NOW)
    assert res.found and "p9" not in {x.prediction_id for x in res.legs}
    assert len({x.match_key for x in res.legs}) == len(res.legs)


def test_prefer_value_uses_value_legs_when_possible():
    legs = [leg(0, 2.0, .6), leg(1, 2.0, .6), leg(2, 2.0, .4, value=True), leg(3, 2.0, .4, value=True)]
    res = build_target_slip(legs, 4.0, now=NOW, max_legs=2, prefer_value=True)
    assert all(x.value_flag for x in res.legs) and res.message.startswith("Built from VALUE legs")


def test_target_must_exceed_one():
    with pytest.raises(ValueError):
        build_target_slip([], 1.0)


def test_weekly_jackpot_two_per_day():
    week = iso_week_days(DAY)
    legs = [leg(i * 10 + j, 2.0, 0.4 + 0.05 * j, day=d) for i, d in enumerate(week) for j in range(3)]
    j = weekly_jackpot(legs, DAY)
    assert j["week_start"] == week[0] and j["complete"]
    for d in j["days"]:
        assert len(d["legs"]) == 2
        assert sorted(x.probability for x in d["legs"]) == [0.45, 0.5]
    assert math.isclose(j["week_combined_probability"], (0.45 * 0.5) ** 7, rel_tol=1e-3)


def test_weekly_jackpot_reports_incomplete_days():
    j = weekly_jackpot([leg(1, 2.0, .6)], DAY)
    assert not j["complete"] and "fewer published picks" in j["note"]


def test_top_n_orders_by_confidence_and_limits():
    legs = [leg(i, 2.0, p) for i, p in enumerate([.4, .9, .6, .7, .5])]
    top = top_n(legs, DAY, 3)
    assert [x.probability for x in top] == [.9, .7, .6]
