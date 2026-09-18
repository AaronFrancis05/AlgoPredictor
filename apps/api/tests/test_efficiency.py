"""Caching and conditional-request behaviour of the prediction endpoints."""
from datetime import UTC, datetime, timedelta

from app.core.redis import get_redis
from app.services import livescores
from tests.helpers import give_plan, login, register_verified
from tests.test_picks_api import make_picks, publish, signed


async def test_unchanged_poll_gets_304_and_a_change_gets_a_new_etag(client):
    day = datetime.now(UTC).date() + timedelta(days=5)
    await publish(client, make_picks(day, 3, prefix="etg"))
    r = await client.get("/api/v1/picks", params={"date": day.isoformat()})
    tag = r.headers["etag"]
    assert r.status_code == 200 and tag.startswith('W/"')
    again = await client.get("/api/v1/picks", params={"date": day.isoformat()}, headers={"if-none-match": tag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == tag
    await publish(client, make_picks(day, 4, prefix="etg2"))  # a new pick for the day invalidates the cache
    changed = await client.get("/api/v1/picks", params={"date": day.isoformat()}, headers={"if-none-match": tag})
    assert changed.status_code == 200 and changed.headers["etag"] != tag


async def test_errors_are_not_given_etags(client):
    r = await client.get("/api/v1/picks/top")
    assert r.status_code == 401 and "etag" not in r.headers


async def test_closed_account_loses_access_at_once_despite_viewer_cache(client):
    email = await register_verified(client)
    await give_plan(email, "pro")
    data = await login(client, email)
    day = datetime.now(UTC).date() + timedelta(days=6)
    await publish(client, make_picks(day, 3, prefix="vwr"))
    assert (await client.get("/api/v1/picks/top", params={"date": day.isoformat()})).status_code == 200  # cached
    access = client.cookies.get("ap_access")
    assert access
    r = await client.delete("/api/v1/me", headers={"x-csrf-token": data["csrf_token"]})
    assert r.status_code == 200, r.text
    # the access token is still unexpired, but the cached viewer was dropped with the account
    r = await client.get("/api/v1/picks/top", params={"date": day.isoformat()},
                         headers={"authorization": f"Bearer {access}"})
    assert r.status_code == 401


async def test_age_confirmation_reaches_cached_viewer(client):
    """A user whose viewer was cached before confirming age sees picks right after confirming."""
    from sqlalchemy import update

    from app.db.session import get_sessionmaker
    from app.models import User

    email = await register_verified(client)
    async with get_sessionmaker()() as db:
        await db.execute(update(User).where(User.email == email).values(age_confirmed_at=None))
        await db.commit()
    data = await login(client, email)
    assert (await client.get("/api/v1/picks/history")).status_code == 403  # caches the unconfirmed viewer
    r = await client.post("/api/v1/auth/confirm-age", json={"confirm_age_18": True},
                          headers={"x-csrf-token": data["csrf_token"]})
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/picks/history")).status_code == 200


async def test_history_pages_cover_every_played_match_once(client):
    day = datetime.now(UTC).date() - timedelta(days=3)
    picks = make_picks(day, 18, prefix="hpg")
    await publish(client, picks)
    results = [dict(prediction_id=p["prediction_id"], result="home", correct=i % 2 == 0, rps=0.2)
               for i, p in enumerate(picks)]
    raw, headers = signed({"results": results})
    assert (await client.post("/internal/ingest/results", content=raw, headers=headers)).status_code == 200
    await login(client, await register_verified(client))
    q = {"date_from": day.isoformat(), "date_to": day.isoformat(), "page_size": 10}
    pages = [(await client.get("/api/v1/picks/history", params={**q, "page": n})).json() for n in (1, 2)]
    ids = [p["prediction_id"] for page in pages for p in page["picks"]]
    assert sorted(ids) == sorted(p["prediction_id"] for p in picks) and len(pages[1]["picks"]) == 8
    s = pages[0]["summary"]
    assert (s["matches"], s["won"], s["lost"]) == (18, 9, 9) and pages[0]["total"] == 18
    won = (await client.get("/api/v1/picks/history", params={**q, "outcome": "won"})).json()
    assert won["total"] == 9 and all(p["outcome"] == "won" for p in won["picks"])


async def test_track_record_aggregates(client):
    day = datetime.now(UTC).date() - timedelta(days=40)
    picks = make_picks(day, 6, prefix="agg")
    await publish(client, picks)
    results = [dict(prediction_id=p["prediction_id"], result="home", correct=i < 4, rps=0.1 * (i + 1))
               for i, p in enumerate(picks)]
    raw, headers = signed({"results": results})
    assert (await client.post("/internal/ingest/results", content=raw, headers=headers)).status_code == 200
    tr = (await client.get("/api/v1/track-record")).json()
    month = next(m for m in tr["by_month"] if m["month"] == day.strftime("%Y-%m"))
    assert month["graded"] >= 6
    assert sum(t["graded"] for t in tr["by_tier"]) == tr["graded"]
    assert len(tr["recent"]) <= 20 and tr["recent"] == sorted(tr["recent"], key=lambda p: p["kickoff_at"],
                                                              reverse=True)


async def test_live_list_announces_the_next_kickoff(client):
    """Without a live feed, the live list next changes when the next published match kicks off."""
    soon = (datetime.now(UTC) + timedelta(hours=3)).replace(second=0, microsecond=0)
    picks = make_picks(soon.date(), 1, prefix="nko")
    picks[0]["time"] = soon.astimezone(livescores.UK).strftime("%H:%M")
    picks[0]["date"] = soon.astimezone(livescores.UK).date().isoformat()
    picks[0]["home_team"], picks[0]["away_team"] = "Kickoff Hint Home", "Kickoff Hint Away"  # unique in shared DB
    await publish(client, picks)
    try:
        body = (await client.get("/api/v1/picks/live")).json()
        assert body["picks"] == [] and body["feed"] is False
        assert datetime.fromisoformat(body["next_update_at"]) <= soon
    finally:  # a match a few hours ahead would otherwise join other tests' live-score linking
        from sqlalchemy import delete

        from app.db.session import get_sessionmaker
        from app.models import Pick
        async with get_sessionmaker()() as db:
            await db.execute(delete(Pick).where(Pick.prediction_id == picks[0]["prediction_id"]))
            await db.commit()


async def test_next_update_hint():
    now = datetime.now(UTC).replace(microsecond=0)
    redis = get_redis()
    assert await livescores.next_update_at(now) is None
    await redis.set("livescore:last_poll", (now - timedelta(seconds=30)).isoformat())
    await redis.set("livescore:interval", "300")
    assert await livescores.next_update_at(now) == now + timedelta(seconds=270)
    await redis.set("livescore:interval", "40")  # due already: never sooner than the next worker tick
    assert await livescores.next_update_at(now) == now + timedelta(seconds=60)
    await redis.set("livescore:paused", "1")
    assert await livescores.next_update_at(now) is None
