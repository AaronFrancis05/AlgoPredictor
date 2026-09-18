"""Product logic on top of published picks: target-odds slips, weekly jackpot, daily top-N.

Pure functions (no DB, no I/O) so they are easy to test. Probabilities are the model's own; combined
probabilities multiply leg probabilities, which assumes the matches are independent - this is stated
in every response.
"""
import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

ODDS_MIN, ODDS_MAX = 1.20, 2.50
INDEPENDENCE_NOTE = ("Combined probability multiplies the model's leg probabilities and assumes the matches "
                     "are independent. It is an estimate, not a guarantee.")


@dataclass(frozen=True)
class Leg:
    prediction_id: str
    kickoff_date: date
    kickoff_at: datetime
    league_code: str
    home_team: str
    away_team: str
    pick: str
    probability: float          # model probability of the picked outcome (= confidence)
    tier: str
    odds: float | None
    value_flag: bool = False

    @property
    def match_key(self) -> tuple:
        return (self.kickoff_date, self.home_team, self.away_team)


@dataclass
class SlipResult:
    legs: list[Leg] = field(default_factory=list)
    target_odds: float | None = None
    combined_odds: float | None = None
    combined_probability: float | None = None
    expected_value: float | None = None
    found: bool = False
    message: str = ""


def _one_per_match(legs: Iterable[Leg]) -> list[Leg]:
    best: dict[tuple, Leg] = {}
    for leg in legs:
        cur = best.get(leg.match_key)
        if cur is None or leg.probability > cur.probability:
            best[leg.match_key] = leg
    return list(best.values())


def build_target_slip(legs: Sequence[Leg], target_odds: float, *, tolerance: float = 0.15,
                      min_legs: int = 2, max_legs: int = 6, pool_size: int = 20,
                      prefer_value: bool = False, now: datetime | None = None) -> SlipResult:
    """Pick 2-6 legs (one per match, odds 1.20-2.50, not yet started) whose combined odds are within
    +-tolerance of target_odds, maximising combined model probability (tie-break: expected value).
    Returns found=False rather than padding the slip when no combination fits."""
    if target_odds <= 1.0:
        raise ValueError("target_odds must be greater than 1")
    lo, hi = target_odds * (1 - tolerance), target_odds * (1 + tolerance)
    eligible = [leg for leg in legs if leg.odds is not None and ODDS_MIN <= leg.odds <= ODDS_MAX
                and (now is None or leg.kickoff_at > now)]
    eligible = _one_per_match(eligible)

    def search(pool: list[Leg]) -> SlipResult | None:
        pool = sorted(pool, key=lambda x: x.probability, reverse=True)[:pool_size]
        best: tuple[float, float, tuple[Leg, ...]] | None = None
        for k in range(min_legs, max_legs + 1):
            if len(pool) < k:
                break
            # prune: even the k highest odds cannot reach the lower bound
            top_odds = sorted((leg.odds for leg in pool), reverse=True)[:k]
            if math.prod(top_odds) < lo:
                continue
            for combo in itertools.combinations(pool, k):
                odds = math.prod(leg.odds for leg in combo)
                if not lo <= odds <= hi:
                    continue
                prob = math.prod(leg.probability for leg in combo)
                ev = prob * odds - 1
                if best is None or (prob, ev) > (best[0], best[1]):
                    best = (prob, ev, combo)
        if best is None:
            return None
        prob, ev, combo = best
        return SlipResult(legs=sorted(combo, key=lambda x: x.kickoff_at), target_odds=target_odds,
                          combined_odds=round(math.prod(leg.odds for leg in combo), 2),
                          combined_probability=round(prob, 4), expected_value=round(ev, 4), found=True,
                          message=INDEPENDENCE_NOTE)

    if prefer_value:
        res = search([leg for leg in eligible if leg.value_flag])
        if res:
            res.message = "Built from VALUE legs only. " + res.message
            return res
    res = search(eligible)
    if res:
        return res
    return SlipResult(target_odds=target_odds, found=False,
                      message=(f"No combination of {min_legs}-{max_legs} upcoming picks with odds "
                               f"{ODDS_MIN:.2f}-{ODDS_MAX:.2f} lands within {tolerance:.0%} of {target_odds:.2f}. "
                               "The slip is not padded with weaker legs."))


def iso_week_days(any_day: date) -> list[date]:
    monday = any_day - timedelta(days=any_day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def weekly_jackpot(legs: Sequence[Leg], week_of: date, per_day: int = 2) -> dict:
    """The `per_day` highest-confidence picks (different matches) for each day of the ISO week."""
    by_day: dict[date, list[Leg]] = {d: [] for d in iso_week_days(week_of)}
    for leg in _one_per_match(legs):
        if leg.kickoff_date in by_day:
            by_day[leg.kickoff_date].append(leg)
    days, week_prob, complete = [], 1.0, True
    for d, day_legs in by_day.items():
        chosen = sorted(day_legs, key=lambda x: x.probability, reverse=True)[:per_day]
        prob = math.prod(leg.probability for leg in chosen) if chosen else None
        if len(chosen) < per_day:
            complete = False
        if prob is not None:
            week_prob *= prob
        days.append(dict(date=d, legs=chosen, combined_probability=round(prob, 4) if prob is not None else None,
                         complete=len(chosen) == per_day))
    return dict(week_start=days[0]["date"], days=days, complete=complete,
                # significant figures, not decimals: 14-leg products are tiny (e.g. 2.9e-05)
                week_combined_probability=float(f"{week_prob:.6g}") if any(x["legs"] for x in days) else None,
                note=INDEPENDENCE_NOTE + (" Some days have fewer published picks than requested."
                                          if not complete else ""))


def top_n(legs: Sequence[Leg], day: date, n: int = 10) -> list[Leg]:
    """The n highest-confidence picks of a day (one per match)."""
    same_day = [leg for leg in _one_per_match(legs) if leg.kickoff_date == day]
    return sorted(same_day, key=lambda x: (x.probability, x.kickoff_at), reverse=True)[:n]
