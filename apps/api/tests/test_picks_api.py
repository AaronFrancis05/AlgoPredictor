import json
import time
from datetime import UTC, datetime, timedelta

from app.core.security import sign_payload
from tests.helpers import give_plan, login, register_verified

SECRET = "test-ingest-secret"


def signed(body: dict, ts: int | None = None) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    t = str(ts or int(time.time()))
    sig = sign_payload(SECRET, t, raw)
    return raw, {"content-type": "application/json", "x-ap-timestamp": t, "x-ap-signature": sig}


def make_picks(day, n=12, prefix="t"):
    out = []
    for i in range(n):
        conf = round(0.40 + 0.03 * i, 3)
        out.append(dict(prediction_id=f"{prefix}{day:%m%d}{i:02d}", made_at=datetime.now(UTC).isoformat(),
                        model_version="vtest", date=day.isoformat(), time="23:59", league_code="E0",
                        home_team=f"Home{i}", away_team=f"Away{i}", p_home=conf, p_draw=round((1 - conf) / 2, 3),
                        p_away=round(1 - conf - round((1 - conf) / 2, 3), 3), pick="home", confidence=conf,
                        tier="Strong" if conf >= .65 else "Medium" if conf >= .5 else "Lean",
                        odds_used=round(min(2.45, max(1.25, 1 / conf * 0.95)), 2), odds_source="test",
                        edge=0.06 if i % 3 == 0 else -0.02, value_flag="VALUE" if i % 3 == 0 else ""))
    return out


async def publish(client, picks):
    raw, headers = signed({"picks": picks})
    r = await client.post("/internal/ingest/picks", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_ingest_signature_replay_and_idempotency(client):
    day = datetime.now(UTC).date() + timedelta(days=1)
    picks = make_picks(day, 3, prefix="ing")
    raw, headers = signed({"picks": picks})
    bad = dict(headers, **{"x-ap-signature": "0" * 64})
    assert (await client.post("/internal/ingest/picks", content=raw, headers=bad)).status_code == 401
    old_raw, old_headers = signed({"picks": picks}, ts=int(time.time()) - 3600)
    assert (await client.post("/internal/ingest/picks", content=old_raw, headers=old_headers)).status_code == 401
    r = await client.post("/internal/ingest/picks", content=raw, headers=headers)
    assert r.json() == {"received": 3, "inserted": 3, "skipped_existing": 0}
    assert (await client.post("/internal/ingest/picks", content=raw, headers=headers)).status_code == 409
    # a fresh, correctly signed request with the same rows inserts nothing (published rows are permanent)
    raw2, headers2 = signed({"picks": picks}, ts=int(time.time()) + 1)
    r = await client.post("/internal/ingest/picks", content=raw2, headers=headers2)
    assert r.json() == {"received": 3, "inserted": 0, "skipped_existing": 3}


async def test_free_plan_sees_three_picks_revealed_close_to_kickoff(client):
    day = datetime.now(UTC).date() + timedelta(days=2)
    await publish(client, make_picks(day, 6, prefix="free"))
    r = await client.get("/api/v1/picks", params={"date": day.isoformat()})
    data = r.json()
    assert data["plan"] == "free" and data["total_published"] == 6
    assert all(p["locked"] for p in data["picks"])  # kick-off is more than 2 hours away
    assert all(p["pick"] is None and p["confidence"] is None for p in data["picks"])
    assert "not certainties" in data["disclaimer"]


async def test_pro_sees_all_picks_but_not_value_flags(client):
    day = datetime.now(UTC).date() + timedelta(days=3)
    await publish(client, make_picks(day, 6, prefix="pro"))
    email = await register_verified(client)
    await give_plan(email, "pro")
    await login(client, email)
    data = (await client.get("/api/v1/picks", params={"date": day.isoformat()})).json()
    assert data["plan"] == "pro" and data["hidden_count"] == 0
    assert all(p["pick"] == "home" and p["value_flag"] is None for p in data["picks"])
    assert all(p["tier_hit_rate"] is not None for p in data["picks"])
    top = (await client.get("/api/v1/picks/top", params={"date": day.isoformat(), "n": 3})).json()
    assert [p["confidence"] for p in top["picks"]] == sorted([p["confidence"] for p in top["picks"]], reverse=True)
    assert (await client.get("/api/v1/jackpot")).status_code == 403


async def test_slip_builder_quota_and_result(client):
    day = datetime.now(UTC).date() + timedelta(days=4)
    await publish(client, make_picks(day, 12, prefix="slp"))
    email = await register_verified(client)
    await give_plan(email, "pro")
    data = await login(client, email)
    h = {"x-csrf-token": data["csrf_token"]}
    body = {"target_odds": 5.0, "date_from": day.isoformat(), "date_to": day.isoformat()}
    r = await client.post("/api/v1/slips", json=body, headers=h)
    assert r.status_code == 200, r.text
    slip = r.json()
    assert slip["found"] and 4.25 <= slip["combined_odds"] <= 5.75 and slip["remaining_today"] == 4
    for _ in range(4):
        assert (await client.post("/api/v1/slips", json=body, headers=h)).status_code == 200
    r = await client.post("/api/v1/slips", json=body, headers=h)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "slip_quota"
    assert (await client.post("/api/v1/slips", json={"target_odds": 0.5}, headers=h)).status_code == 422


async def test_elite_gets_jackpot_and_value_flags(client):
    today = datetime.now(UTC).date()
    for d in range(7):
        await publish(client, make_picks(today + timedelta(days=d), 3, prefix=f"jp{d}"))
    email = await register_verified(client)
    await give_plan(email, "elite")
    await login(client, email)
    r = await client.get("/api/v1/jackpot", params={"week_of": today.isoformat()})
    assert r.status_code == 200
    j = r.json()
    assert len(j["days"]) == 7 and "independent" in j["note"]
    for day in j["days"]:
        assert len(day["legs"]) <= 2
    data = (await client.get("/api/v1/picks", params={"date": today.isoformat()})).json()
    assert any(p["value_flag"] is True for p in data["picks"])


async def test_unauthenticated_products_are_rejected(client):
    assert (await client.get("/api/v1/picks/top")).status_code == 401
    assert (await client.post("/api/v1/slips", json={"target_odds": 5})).status_code == 401


async def test_results_ingest_feeds_track_record(client):
    day = datetime.now(UTC).date() - timedelta(days=1)
    picks = make_picks(day, 4, prefix="trk")
    await publish(client, picks)
    results = [dict(prediction_id=p["prediction_id"], result="home" if i % 2 == 0 else "away",
                    correct=i % 2 == 0, rps=0.1 if i % 2 == 0 else 0.4) for i, p in enumerate(picks)]
    raw, headers = signed({"results": results})
    r = await client.post("/internal/ingest/results", content=raw, headers=headers)
    assert r.json()["inserted"] == 4
    tr = (await client.get("/api/v1/track-record")).json()
    assert tr["graded"] >= 4 and tr["backtest"]["bookmaker_rps"] > 0
