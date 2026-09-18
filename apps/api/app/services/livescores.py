"""Live scores for published matches, and each match's phase (upcoming -> live -> finished).

Display only. Grading and the model never read this feed: the official result still comes from the pipeline's
review.py (football-data.co.uk). A full-time score from the feed is shown as provisional until then.

Feed: API-Football v3 (https://v3.football.api-sports.io, header x-apisports-key). Two request types:
  * fixtures?date=YYYY-MM-DD&timezone=UTC  - the day's fixture list, used to link our matches to feed fixtures
  * fixtures?ids=1-2-3 (at most 20 ids)      - current score/status of linked matches while they are in play
Every request counts against a daily budget (LIVESCORE_DAILY_BUDGET, the free plan allows 100) and the poll
interval stretches so the remaining budget lasts until the day's last match ends.

Linking never guesses: a feed fixture is linked when it kicks off within 20 minutes of our kick-off and both team
names are equal after normalisation (accents, punctuation, "FC"-style prefixes removed) or through an alias an
admin confirmed; or when exactly one fixture at that kick-off has one of our teams on the same side (a club cannot
play two matches at once). Anything else waits for an admin to pick the fixture, which also stores the aliases.
"""
import json
import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached, invalidate
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models import LiveMatch, LiveTeamAlias, Pick

log = get_logger(__name__)

PROVIDER = "api_football"
CACHE_NS = "live"
UK = ZoneInfo("Europe/London")
IN_PLAY = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
FINAL = {"FT", "AET", "PEN", "AWD", "WO"}
CALLED_OFF = {"PST": "postponed", "CANC": "cancelled", "ABD": "abandoned"}
KICKOFF_TOLERANCE = timedelta(minutes=20)
LINK_AHEAD = timedelta(hours=30)          # link matches up to this far ahead
TRACK_BACK = timedelta(hours=4)           # keep polling a match this long after kick-off (delays, extra time)
MAX_IDS = 20                              # provider limit for fixtures?ids=
MAX_CANDIDATES = 25

# Legal-form and club-type words that one source writes and the other drops ("VfL Wolfsburg" / "Wolfsburg").
_NOISE = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "ssc", "fk", "sk", "bk", "if", "cd", "ud", "sd", "rc", "rcd",
          "sv", "fsv", "tsv", "vfl", "vfb", "tsg", "spvgg", "bsc", "ssv", "us", "cfc", "club", "calcio", "1"}


# ---------------------------------------------------------------------------------------------- names and keys
def match_key(day: date | str, home: str, away: str) -> str:
    return f"{day if isinstance(day, str) else day.isoformat()}|{home}|{away}"


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _NOISE]
    return " ".join(words)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass(frozen=True)
class FeedFixture:
    id: int
    kickoff_at: datetime
    home: str
    away: str
    league: str
    country: str
    status: str
    elapsed: int | None
    home_goals: int | None
    away_goals: int | None

    def brief(self) -> dict:
        return dict(id=self.id, kickoff_at=self.kickoff_at.isoformat(), home=self.home, away=self.away,
                    league=self.league, country=self.country)


def parse_fixture(item: dict) -> FeedFixture | None:
    try:
        fx, teams, goals = item["fixture"], item["teams"], item.get("goals") or {}
        status = fx.get("status") or {}
        return FeedFixture(id=int(fx["id"]), kickoff_at=datetime.fromtimestamp(int(fx["timestamp"]), UTC),
                           home=str(teams["home"]["name"]), away=str(teams["away"]["name"]),
                           league=str((item.get("league") or {}).get("name") or ""),
                           country=str((item.get("league") or {}).get("country") or ""),
                           status=str(status.get("short") or ""), elapsed=status.get("elapsed"),
                           home_goals=goals.get("home"), away_goals=goals.get("away"))
    except (KeyError, TypeError, ValueError):
        return None


def choose_link(home: str, away: str, kickoff_at: datetime, uk_day: date | None, fixtures: Iterable[FeedFixture],
                aliases: dict[str, str], taken: set[int]) -> tuple[FeedFixture | None, str, list[FeedFixture]]:
    """(fixture, method, candidates). method is "exact", "one_side" or "" (not linked).
    uk_day is the UK date when our match has no kick-off time: then any fixture that day is a candidate, and
    only an exact two-team match links automatically."""
    def canon(feed_name: str) -> str:
        n = normalise(feed_name)
        return normalise(aliases[n]) if n in aliases else n

    near = sorted((f for f in fixtures if f.id not in taken and _near(f, kickoff_at, uk_day)),
                  key=lambda f: abs(f.kickoff_at - kickoff_at))
    h, a = normalise(home), normalise(away)
    exact = [f for f in near if canon(f.home) == h and canon(f.away) == a]
    if len(exact) == 1:
        return exact[0], "exact", near
    if not exact and uk_day is None:
        side = [f for f in near if canon(f.home) == h or canon(f.away) == a]
        if len(side) == 1:
            return side[0], "one_side", near
    return None, "", near


# ---------------------------------------------------------------------------------------------- phases
def phase_of(kickoff_at: datetime, result: str | None, live: dict | None, now: datetime,
             has_time: bool = True) -> str:
    """upcoming | live | finished | awaiting_result | postponed | cancelled | abandoned.
    Without a feed state a match counts as live for MATCH_LIVE_MINUTES after kick-off. A match without a published
    kick-off time (stored as 00:00 UK) stays upcoming for its whole day, as its real start is unknown."""
    if result is not None:
        return "finished"
    status = (live or {}).get("status") or ""
    if status in CALLED_OFF:
        return CALLED_OFF[status]
    if status in FINAL:
        return "finished"
    if status in IN_PLAY:
        return "live"
    if not has_time:
        return "upcoming" if now < kickoff_at + timedelta(days=1) else "awaiting_result"
    if now < kickoff_at:
        return "upcoming"
    if now < kickoff_at + timedelta(minutes=get_settings().match_live_minutes):
        return "live"
    return "awaiting_result"


def outcome_from_goals(home_goals: int | None, away_goals: int | None) -> str | None:
    if home_goals is None or away_goals is None:
        return None
    return "home" if home_goals > away_goals else "away" if away_goals > home_goals else "draw"


async def live_states(db: AsyncSession, start: date, end: date) -> dict[str, dict]:
    """Feed state per match_key for kick-off dates in [start, end]; cached briefly, dropped after each poll."""
    async def load() -> dict[str, dict]:
        rows = (await db.execute(select(LiveMatch).where(LiveMatch.kickoff_date >= start,
                                                         LiveMatch.kickoff_date <= end,
                                                         LiveMatch.fixture_id.is_not(None)))).scalars().all()
        return {r.match_key: dict(status=r.status, elapsed=r.elapsed, home_goals=r.home_goals,
                                  away_goals=r.away_goals,
                                  updated_at=_aware(r.updated_at).isoformat() if r.updated_at else None)
                for r in rows if r.status}

    return await cached(CACHE_NS, f"{start}:{end}", 30, load)


# ---------------------------------------------------------------------------------------------- provider client
def _calls_key(now: datetime) -> str:
    return f"livescore:calls:{now:%Y-%m-%d}"


async def budget_left(now: datetime) -> int:
    s = get_settings()
    used = int(await get_redis().get(_calls_key(now)) or 0)
    reported = await get_redis().get("livescore:remaining")
    left = s.livescore_daily_budget - used
    if reported is not None:
        left = min(left, int(reported))
    return max(0, left)


async def _get(params: dict, now: datetime) -> list[dict] | None:
    """One provider request, counted against the daily budget. None = not sent or failed (logged)."""
    s = get_settings()
    key = s.api_football_key.get_secret_value()
    redis = get_redis()
    if not key:
        return None
    if await redis.get("livescore:paused"):
        return None
    if await budget_left(now) <= 0:
        log.warning("livescore_budget_exhausted", budget=s.livescore_daily_budget)
        return None
    calls = _calls_key(now)
    await redis.incr(calls)
    await redis.expire(calls, 2 * 86400)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{s.api_football_url.rstrip('/')}/fixtures", params=params,
                                 headers={"x-apisports-key": key})
    except httpx.HTTPError as e:
        await redis.set("livescore:last_error", f"{now:%H:%M} network: {e}"[:300], ex=86400)
        log.warning("livescore_request_failed", error=str(e))
        return None
    remaining = r.headers.get("x-ratelimit-requests-remaining")
    if remaining is not None and remaining.lstrip("-").isdigit():
        await redis.set("livescore:remaining", remaining, ex=6 * 3600)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    errors = body.get("errors") if isinstance(body, dict) else None
    if r.status_code != 200 or errors:
        msg = f"{now:%H:%M} HTTP {r.status_code}: {errors or r.text[:200]}"[:300]
        await redis.set("livescore:last_error", msg, ex=86400)
        await redis.set("livescore:paused", "1", ex=3600)  # bad key / plan limit: back off for an hour
        log.warning("livescore_provider_error", status=r.status_code, errors=str(errors)[:300])
        return None
    return body.get("response") or []


async def fetch_day(day: date, now: datetime) -> list[FeedFixture] | None:
    items = await _get({"date": day.isoformat(), "timezone": "UTC"}, now)
    if items is None:
        return None
    await get_redis().set(f"livescore:day_fetched:{day}", now.isoformat(), ex=2 * 86400)
    return [f for f in map(parse_fixture, items) if f is not None]


async def fetch_ids(ids: list[int], now: datetime) -> list[FeedFixture] | None:
    items = await _get({"ids": "-".join(map(str, ids))}, now)
    return None if items is None else [f for f in map(parse_fixture, items) if f is not None]


# ---------------------------------------------------------------------------------------------- sync, link, poll
async def ensure_rows(db: AsyncSession, now: datetime) -> None:
    """One live_matches row per published match that kicks off between TRACK_BACK ago and LINK_AHEAD."""
    q = (select(Pick.kickoff_date, Pick.kickoff_at, Pick.league_code, Pick.home_team, Pick.away_team)
         .where(Pick.kickoff_at >= now - TRACK_BACK, Pick.kickoff_at <= now + LINK_AHEAD, Pick.is_demo.is_(False))
         .distinct())
    matches = {match_key(d, h, a): (d, _aware(k), lg, h, a) for d, k, lg, h, a in (await db.execute(q)).all()}
    if not matches:
        return
    have = set((await db.execute(select(LiveMatch.match_key)
                                 .where(LiveMatch.match_key.in_(list(matches))))).scalars())
    for key, (d, k, lg, h, a) in matches.items():
        if key not in have:
            db.add(LiveMatch(match_key=key, kickoff_date=d, kickoff_at=k, league_code=lg, home_team=h, away_team=a,
                             provider=PROVIDER, link_method="", candidates=[], status=""))
    await db.commit()


async def _aliases(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(LiveTeamAlias).where(LiveTeamAlias.provider == PROVIDER))).scalars().all()
    return {r.provider_name: r.team for r in rows}


def _near(f: FeedFixture, kickoff_at: datetime, uk_day: date | None) -> bool:
    """Is feed fixture f a candidate for our match? uk_day is set when we have no kick-off time."""
    if uk_day is not None:
        return f.kickoff_at.astimezone(UK).date() == uk_day
    return abs(f.kickoff_at - kickoff_at) <= KICKOFF_TOLERANCE


async def _timeless(db: AsyncSession, now: datetime) -> set[str]:
    """match_keys of published matches without a kick-off time (the ingest stores 00:00 UK for them)."""
    rows = (await db.execute(select(Pick.kickoff_date, Pick.home_team, Pick.away_team).where(
        Pick.kickoff_time == "", Pick.kickoff_at >= now - TRACK_BACK - timedelta(days=1),
        Pick.kickoff_at <= now + LINK_AHEAD))).all()
    return {match_key(d, h, a) for d, h, a in rows}


async def link_matches(db: AsyncSession, now: datetime, force: bool = False) -> int:
    """Link unlinked matches to feed fixtures, fetching a day's fixture list when it is stale. Returns links made."""
    redis = get_redis()
    unlinked = (await db.execute(select(LiveMatch).where(
        LiveMatch.fixture_id.is_(None), LiveMatch.kickoff_at >= now - TRACK_BACK,
        LiveMatch.kickoff_at <= now + LINK_AHEAD))).scalars().all()
    if not unlinked:
        return 0
    timeless = await _timeless(db, now)
    targets = [(m, _aware(m.kickoff_at), m.kickoff_date if m.match_key in timeless else None) for m in unlinked]
    # UTC days to list: a timeless UK day spans two UTC days
    days = sorted({k.date() for _, k, u in targets if u is None}
                  | {d for _, _, u in targets if u is not None for d in (u, u + timedelta(days=1))})
    feed: list[FeedFixture] = []
    for day in days:
        soonest = min((k for _, k, _ in targets if k.date() == day), default=now + LINK_AHEAD)
        fetched = await redis.get(f"livescore:day_fetched:{day}")
        age = now - datetime.fromisoformat(fetched) if fetched else None
        # a fresh list every 3 h; hourly once a match of that day is less than an hour away
        stale = age is None or age > timedelta(hours=3) or (soonest - now < timedelta(hours=1)
                                                             and age > timedelta(hours=1))
        got = await fetch_day(day, now) if stale or force else None
        if got is not None:
            # keep only fixtures near one of our kick-offs: small for Redis, enough for the admin's choices
            got = [f for f in got if any(_near(f, k, u) for _, k, u in targets)]
            await redis.set(f"livescore:day:{day}", _dump(got), ex=2 * 86400)
            feed.extend(got)
        elif cached_list := await redis.get(f"livescore:day:{day}"):
            feed.extend(_load(cached_list))
    if not feed:
        return 0
    aliases = await _aliases(db)
    taken = set((await db.execute(select(LiveMatch.fixture_id).where(LiveMatch.fixture_id.is_not(None),
                                                                     LiveMatch.kickoff_at >= now - timedelta(days=2))
                                 )).scalars())
    made = 0
    for m, kickoff_at, uk_day in targets:
        fx, method, near = choose_link(m.home_team, m.away_team, kickoff_at, uk_day, feed, aliases, taken)
        m.candidates = [f.brief() for f in near[:MAX_CANDIDATES]]
        if fx is not None:
            _apply_link(m, fx, method, now)
            taken.add(fx.id)
            made += 1
    await db.commit()
    if made:
        await invalidate(CACHE_NS)
        log.info("livescore_linked", count=made)
    return made


def _apply_link(m: LiveMatch, fx: FeedFixture, method: str, now: datetime) -> None:
    m.fixture_id, m.link_method, m.linked_at, m.provider = fx.id, method, now, PROVIDER
    _apply_state(m, fx, now)


def _apply_state(m: LiveMatch, fx: FeedFixture, now: datetime) -> bool:
    new = (fx.status, fx.elapsed, fx.home_goals, fx.away_goals)
    if new == (m.status, m.elapsed, m.home_goals, m.away_goals):
        return False
    m.status, m.elapsed, m.home_goals, m.away_goals, m.updated_at = (*new, now)
    return True


def _dump(fixtures: list[FeedFixture]) -> str:
    return json.dumps([f.brief() for f in fixtures])


def _load(raw: str) -> list[FeedFixture]:
    out = []
    for d in json.loads(raw):
        out.append(FeedFixture(id=d["id"], kickoff_at=datetime.fromisoformat(d["kickoff_at"]), home=d["home"],
                               away=d["away"], league=d["league"], country=d["country"], status="", elapsed=None,
                               home_goals=None, away_goals=None))
    return out


def poll_interval(now: datetime, last_end: datetime, calls_left: int, requests_per_poll: int) -> float:
    """Seconds between polls so the calls left (minus the reserve) last until the last match ends."""
    s = get_settings()
    usable = calls_left - s.livescore_reserve
    if usable < requests_per_poll:
        return math.inf
    seconds_left = max(60.0, (last_end - now).total_seconds())
    return max(float(s.livescore_min_interval_seconds), seconds_left / (usable / requests_per_poll))


async def poll(db: AsyncSession, now: datetime) -> int:
    """Refresh score/status of linked matches in play. Returns the number of matches whose state changed."""
    redis = get_redis()
    active = (await db.execute(select(LiveMatch).where(
        LiveMatch.fixture_id.is_not(None), LiveMatch.kickoff_at <= now + timedelta(minutes=2),
        LiveMatch.kickoff_at >= now - TRACK_BACK))).scalars().all()
    active = [m for m in active if m.status not in FINAL and m.status not in CALLED_OFF]
    if not active:
        return 0
    todays_last = (await db.execute(select(LiveMatch.kickoff_at).where(
        LiveMatch.fixture_id.is_not(None), LiveMatch.kickoff_at >= now - TRACK_BACK,
        LiveMatch.kickoff_at <= now + timedelta(hours=18)).order_by(LiveMatch.kickoff_at.desc()).limit(1))).scalar()
    last_end = _aware(todays_last) + timedelta(minutes=get_settings().match_live_minutes)
    per_poll = math.ceil(len(active) / MAX_IDS)
    interval = poll_interval(now, last_end, await budget_left(now), per_poll)
    last = await redis.get("livescore:last_poll")
    if interval == math.inf or (last and (now - datetime.fromisoformat(last)).total_seconds() < interval - 5):
        return 0
    await redis.set("livescore:last_poll", now.isoformat(), ex=86400)
    await redis.set("livescore:interval", str(round(interval)), ex=86400)
    by_id = {m.fixture_id: m for m in active}
    ids = list(by_id)
    changed = 0
    for i in range(0, len(ids), MAX_IDS):
        got = await fetch_ids(ids[i:i + MAX_IDS], now)
        if got is None:
            break
        for fx in got:
            m = by_id.get(fx.id)
            if m is not None and _apply_state(m, fx, now):
                changed += 1
    await db.commit()
    if changed:
        await invalidate(CACHE_NS)
    return changed


async def tick(db: AsyncSession, now: datetime | None = None) -> None:
    """Worker entry point (every minute). Does nothing - and costs no provider calls - without a key or matches."""
    if not get_settings().api_football_key.get_secret_value():
        return
    now = now or datetime.now(UTC)
    await ensure_rows(db, now)
    await link_matches(db, now)
    await poll(db, now)


# ---------------------------------------------------------------------------------------------- admin
async def admin_status(db: AsyncSession, now: datetime) -> dict:
    s, redis = get_settings(), get_redis()
    rows = (await db.execute(select(LiveMatch).where(
        LiveMatch.kickoff_at >= now - TRACK_BACK, LiveMatch.kickoff_at <= now + LINK_AHEAD)
        .order_by(LiveMatch.kickoff_at))).scalars().all()

    def row(m: LiveMatch) -> dict:
        return dict(match_key=m.match_key, kickoff_at=_aware(m.kickoff_at).isoformat(), league_code=m.league_code,
                    home_team=m.home_team, away_team=m.away_team, fixture_id=m.fixture_id,
                    link_method=m.link_method, status=m.status, candidates=m.candidates or [])

    return dict(
        configured=bool(s.api_football_key.get_secret_value()),
        budget=s.livescore_daily_budget, calls_left=await budget_left(now),
        provider_remaining=await redis.get("livescore:remaining"),
        last_poll=await redis.get("livescore:last_poll"), poll_interval_seconds=await redis.get("livescore:interval"),
        last_error=await redis.get("livescore:last_error"), paused=bool(await redis.get("livescore:paused")),
        tracked=len(rows),
        linked=sum(1 for m in rows if m.fixture_id is not None),
        unmatched=[row(m) for m in rows if m.fixture_id is None],
        to_review=[row(m) for m in rows if m.link_method == "one_side"],
    )


async def admin_link(db: AsyncSession, key: str, fixture_id: int | None, now: datetime) -> LiveMatch:
    """Link (or unlink with None) a match to a feed fixture chosen by an admin; remembers both team aliases."""
    m = await db.get(LiveMatch, key)
    if m is None:
        raise LookupError(key)
    if fixture_id is None:
        m.fixture_id, m.link_method, m.linked_at = None, "", None
        m.status, m.elapsed, m.home_goals, m.away_goals, m.updated_at = "", None, None, None, None
    else:
        cand = next((c for c in m.candidates or [] if int(c["id"]) == fixture_id), None)
        if cand is None:
            raise ValueError("fixture is not one of this match's candidates")
        m.fixture_id, m.link_method, m.linked_at, m.provider = fixture_id, "admin", now, PROVIDER
        for feed_name, team in ((cand["home"], m.home_team), (cand["away"], m.away_team)):
            n = normalise(feed_name)
            if n != normalise(team):
                await db.merge(LiveTeamAlias(provider=PROVIDER, provider_name=n, team=team))
    await db.commit()
    await invalidate(CACHE_NS)
    return m
