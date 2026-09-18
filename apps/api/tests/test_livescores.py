from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import LiveMatch, LiveTeamAlias
from app.services import livescores as ls
from tests.helpers import give_plan, login, register_verified
from tests.test_picks_api import make_picks, publish, signed

T0 = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)


def fx(i, home, away, at=T0, status="NS", elapsed=None, hg=None, ag=None):
    return ls.FeedFixture(id=i, kickoff_at=at, home=home, away=away, league="L", country="C", status=status,
                          elapsed=elapsed, home_goals=hg, away_goals=ag)


def test_normalise_drops_accents_and_club_prefixes():
    assert ls.normalise("VfL Wolfsburg") == ls.normalise("Wolfsburg") == "wolfsburg"
    assert ls.normalise("Greuther Fürth") == "greuther furth"
    assert ls.normalise("Brighton & Hove Albion") == "brighton and hove albion"
    assert ls.normalise("Bayern München") != ls.normalise("Bayern Munich")  # needs an admin-confirmed alias


def test_choose_link_exact_one_side_and_ambiguous():
    feed = [fx(1, "VfL Wolfsburg", "SV Darmstadt 98", T0), fx(2, "Ajax", "Excelsior", T0),
            fx(3, "Bayern München", "Union Berlin", T0 + timedelta(minutes=5)), fx(4, "Other", "Club", T0)]
    got, how, near = ls.choose_link("Wolfsburg", "Darmstadt 98", T0, None, feed, {}, set())
    assert got.id == 1 and how == "exact" and len(near) == 4
    # one of our teams matches on the same side, and only one fixture at that kick-off has it
    got, how, _ = ls.choose_link("Bayern Munich", "Union Berlin", T0, None, feed, {}, set())
    assert got.id == 3 and how == "one_side"
    # neither name matches: never guessed
    got, how, _ = ls.choose_link("Man City", "Wolves", T0, None, feed, {}, set())
    assert got is None and how == ""
    # an admin-confirmed alias turns it into an exact match
    got, how, _ = ls.choose_link("Bayern Munich", "Union Berlin", T0, None, feed,
                                 {"bayern munchen": "Bayern Munich"}, set())
    assert got.id == 3 and how == "exact"
    # too far from our kick-off, or already linked to another match: not a candidate
    assert ls.choose_link("Ajax", "Excelsior", T0 + timedelta(hours=1), None, feed, {}, set())[0] is None
    assert ls.choose_link("Ajax", "Excelsior", T0, None, feed, {}, {2})[0] is None


def test_phase_without_and_with_feed():
    k = T0
    assert ls.phase_of(k, None, None, k - timedelta(minutes=1)) == "upcoming"
    assert ls.phase_of(k, None, None, k + timedelta(minutes=30)) == "live"
    assert ls.phase_of(k, None, None, k + timedelta(minutes=150)) == "awaiting_result"
    assert ls.phase_of(k, "home", None, k + timedelta(minutes=30)) == "finished"
    assert ls.phase_of(k, None, {"status": "HT"}, k + timedelta(minutes=50)) == "live"
    assert ls.phase_of(k, None, {"status": "FT"}, k + timedelta(minutes=100)) == "finished"
    assert ls.phase_of(k, None, {"status": "PST"}, k - timedelta(hours=1)) == "postponed"
    # a late kick-off the feed still reports as not started: stays live until the fallback window ends
    assert ls.phase_of(k, None, {"status": "NS"}, k + timedelta(minutes=10)) == "live"
    # no published kick-off time: upcoming for the whole day
    assert ls.phase_of(k, None, None, k + timedelta(hours=5), has_time=False) == "upcoming"


def test_poll_interval_spreads_budget_to_the_last_match():
    s = get_settings()
    end = T0 + timedelta(hours=10)
    # 100 calls left, 5 in reserve, 10 hours to go: one poll about every 6.3 minutes
    assert ls.poll_interval(T0, end, 100, 1) == pytest.approx(36000 / 95)
    assert ls.poll_interval(T0, end, 10_000, 1) == s.livescore_min_interval_seconds
    assert ls.poll_interval(T0, end, s.livescore_reserve, 1) == float("inf")


async def test_link_and_poll_updates_scores_within_budget(client, monkeypatch):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    day = now.date()
    picks = make_picks(day, 2, prefix="lv")
    kick = (now - timedelta(minutes=30)).astimezone(ls.UK)
    for p in picks:
        p["date"], p["time"] = kick.date().isoformat(), kick.strftime("%H:%M")
    await publish(client, picks)
    kickoff = kick.astimezone(UTC)
    feed = [fx(101, "Home0 FC", "Away0", kickoff, "2H", 63, 2, 1), fx(102, "Other", "Away1", kickoff, "1H", 30, 0, 0)]
    calls = []

    async def fake_get(params, now_):
        calls.append(params)
        ids = params.get("ids")
        chosen = [f for f in feed if ids is None or str(f.id) in ids.split("-")]
        return [{"fixture": {"id": f.id, "timestamp": int(f.kickoff_at.timestamp()),
                             "status": {"short": f.status, "elapsed": f.elapsed}},
                 "league": {"name": f.league, "country": f.country},
                 "teams": {"home": {"name": f.home}, "away": {"name": f.away}},
                 "goals": {"home": f.home_goals, "away": f.away_goals}} for f in chosen]

    monkeypatch.setattr(ls, "_get", fake_get)
    monkeypatch.setattr(get_settings(), "api_football_key", type(get_settings().api_football_key)("k"))
    async with get_sessionmaker()() as db:
        await ls.tick(db, now)
        rows = {m.home_team: m for m in (await db.execute(select(LiveMatch))).scalars()}
    assert rows["Home0"].fixture_id == 101 and rows["Home0"].link_method == "exact"
    assert rows["Home0"].status == "2H" and (rows["Home0"].home_goals, rows["Home0"].away_goals) == (2, 1)
    assert rows["Home1"].fixture_id == 102 and rows["Home1"].link_method == "one_side"
    assert [c for c in calls if "date" in c] and [c for c in calls if "ids" in c]

    # the second tick a few seconds later is inside the poll interval: no new provider request
    n = len(calls)
    async with get_sessionmaker()() as db:
        await ls.tick(db, now + timedelta(seconds=10))
    assert len(calls) == n

    email = await register_verified(client)
    await give_plan(email, "pro")
    await login(client, email)
    live = (await client.get("/api/v1/picks/live")).json()
    mine = {p["home_team"]: p for p in live["picks"] if p["prediction_id"].startswith("lv")}
    assert mine["Home0"]["phase"] == "live" and mine["Home0"]["live"]["home_goals"] == 2
    assert mine["Home0"]["live"]["elapsed"] == 63

    # full time: the pick (home) won provisionally and the match moves to history
    feed[0] = fx(101, "Home0 FC", "Away0", kickoff, "FT", 90, 2, 1)
    async with get_sessionmaker()() as db:
        await ls.poll(db, now + timedelta(hours=1))
    hist = (await client.get("/api/v1/picks/history")).json()
    done = {p["home_team"]: p for p in hist["picks"] if p["prediction_id"].startswith("lv")}
    assert done["Home0"]["phase"] == "finished" and done["Home0"]["outcome"] == "won"
    assert done["Home0"]["outcome_official"] is False and hist["summary"]["provisional"] >= 1
    assert "Home1" not in done  # still in play


async def test_admin_link_stores_aliases(client):
    now = datetime.now(UTC)
    async with get_sessionmaker()() as db:
        key = ls.match_key(now.date(), "Sp Lisbon", "Arouca")
        db.add(LiveMatch(match_key=key, kickoff_date=now.date(), kickoff_at=now + timedelta(hours=2),
                         league_code="P1", home_team="Sp Lisbon", away_team="Arouca", provider=ls.PROVIDER,
                         link_method="", status="",
                         candidates=[{"id": 7, "home": "Sporting CP", "away": "Arouca", "league": "Liga",
                                      "country": "Portugal", "kickoff_at": now.isoformat()}]))
        await db.commit()
        with pytest.raises(ValueError):
            await ls.admin_link(db, key, 8, now)  # not a candidate
        m = await ls.admin_link(db, key, 7, now)
        assert m.fixture_id == 7 and m.link_method == "admin"
        aliases = (await db.execute(select(LiveTeamAlias))).scalars().all()
        assert [(a.provider_name, a.team) for a in aliases] == [("sporting cp", "Sp Lisbon")]


async def test_day_picks_carry_phase_and_history_hides_upcoming(client):
    now = datetime.now(UTC)
    past = now - timedelta(days=1)
    picks = make_picks(past.date(), 3, prefix="hs")
    await publish(client, picks)
    results = [dict(prediction_id=picks[0]["prediction_id"], result="home", correct=True, rps=0.1),
               dict(prediction_id=picks[1]["prediction_id"], result="away", correct=False, rps=0.5)]
    raw, headers = signed({"results": results})
    assert (await client.post("/internal/ingest/results", content=raw, headers=headers)).status_code == 200
    future = make_picks((now + timedelta(days=1)).date(), 2, prefix="hf")
    await publish(client, future)

    email = await register_verified(client)
    await login(client, email)  # free plan: history still shows every played pick
    day = (await client.get("/api/v1/picks", params={"date": future[0]["date"]})).json()
    assert {p["phase"] for p in day["picks"]} == {"upcoming"}
    hist = (await client.get("/api/v1/picks/history", params={"date_from": past.date().isoformat(),
                                                             "date_to": now.date().isoformat()})).json()
    mine = {p["prediction_id"]: p for p in hist["picks"] if p["prediction_id"].startswith(("hs", "hf"))}
    assert set(mine) == {p["prediction_id"] for p in picks}
    assert mine[picks[0]["prediction_id"]]["outcome"] == "won" and mine[picks[0]["prediction_id"]]["outcome_official"]
    assert mine[picks[1]["prediction_id"]]["outcome"] == "lost"
    assert mine[picks[2]["prediction_id"]]["phase"] == "awaiting_result" and mine[picks[2]["prediction_id"]]["pick"]
    won = (await client.get("/api/v1/picks/history", params={"date_from": past.date().isoformat(),
                                                            "outcome": "won"})).json()
    assert all(p["outcome"] == "won" for p in won["picks"])
    bad = await client.get("/api/v1/picks/history", params={"date_from": "2026-01-01", "date_to": "2026-09-01"})
    assert bad.status_code == 422
    assert (await client.get("/api/v1/picks/history")).status_code in (200,)  # signed in
    await client.post("/api/v1/auth/logout")
    client.cookies.clear()
    assert (await client.get("/api/v1/picks/history")).status_code == 401
