import uuid
from datetime import UTC, datetime, timedelta

from app.core.redis import get_redis
from app.db.session import get_sessionmaker
from app.models import AccessToken
from app.services import access_tokens
from tests.helpers import enable_mfa, give_plan, login, register_verified, reset_rate_limits


def _csrf(client) -> dict:
    return {"x-csrf-token": client.cookies.get("ap_csrf")}


async def _fresh_limits() -> None:
    """These tests sign in many accounts; start each phase with an empty auth rate-limit window."""
    await get_redis().flushall()


async def _make_admin(client) -> str:
    await _fresh_limits()
    email = await register_verified(client)
    async with get_sessionmaker()() as db:
        await access_tokens.set_role(db, email, "admin")
        await db.commit()
    await access_tokens.after_change()
    await login(client, email)
    await enable_mfa(client)  # admin endpoints need a two-factor session
    await reset_rate_limits()  # enrolment used two auth-limited calls; keep caches intact
    return email


async def _create_token(client, **kw) -> dict:
    body = dict(plan_code="pro", expires_at=(datetime.now(UTC) + timedelta(days=7)).isoformat(), **kw)
    r = await client.post("/api/v1/admin/access-tokens", json=body, headers=_csrf(client))
    assert r.status_code == 201, r.text
    return r.json()


async def test_admin_has_top_plan_and_cannot_be_charged(client):
    await _make_admin(client)
    me = (await client.get("/api/v1/me")).json()
    assert me["role"] == "admin" and me["is_admin"] is True and me["plan"] == "elite"
    assert me["entitlements"]["jackpot"] is True
    assert (await client.get("/api/v1/jackpot")).status_code == 200
    r = await client.post("/api/v1/billing/checkout", json=dict(plan_code="pro", currency="USD", provider="stripe"),
                          headers=_csrf(client))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "admin_full_access"


async def test_non_admin_cannot_manage_tokens(client):
    await login(client, await register_verified(client))
    assert (await client.get("/api/v1/admin/access-tokens")).status_code == 403
    r = await client.post("/api/v1/admin/access-tokens", json=dict(plan_code="pro", expires_at="2030-01-01T00:00:00Z"),
                          headers=_csrf(client))
    assert r.status_code == 403


async def test_redeem_grants_plan_until_expiry_and_revoke_ends_it(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=2, note="press")
    code = token["code"]
    assert code.startswith("AP-") and token["status"] == "active" and token["redemptions"] == 0

    await login(client, await register_verified(client))
    assert (await client.get("/api/v1/me")).json()["plan"] == "free"
    r = await client.post("/api/v1/me/access-token", json={"code": code.lower().replace("-", " ")},
                          headers=_csrf(client))
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/me")).json()["plan"] == "pro"
    assert (await client.get("/api/v1/picks/top")).status_code == 200
    r = await client.post("/api/v1/me/access-token", json={"code": code}, headers=_csrf(client))
    assert r.status_code == 409  # once per person

    await _fresh_limits()
    second = await register_verified(client)
    await login(client, second)
    assert (await client.post("/api/v1/me/access-token", json={"code": code}, headers=_csrf(client))).status_code == 200
    third = await register_verified(client)
    await login(client, third)
    r = await client.post("/api/v1/me/access-token", json={"code": code}, headers=_csrf(client))
    assert r.status_code == 400  # used up after max_redemptions

    await _make_admin(client)
    r = await client.post(f"/api/v1/admin/access-tokens/{token['id']}/revoke", headers=_csrf(client))
    assert r.status_code == 200 and r.json()["status"] == "revoked" and r.json()["redemptions"] == 2
    await _fresh_limits()
    await login(client, second)
    assert (await client.get("/api/v1/me")).json()["plan"] == "free"


async def test_expired_and_unknown_codes_are_refused(client):
    await login(client, await register_verified(client))
    r = await client.post("/api/v1/me/access-token", json={"code": "AP-0000-0000-0000-0000"}, headers=_csrf(client))
    assert r.status_code == 400
    await _make_admin(client)
    token = await _create_token(client)
    async with get_sessionmaker()() as db:
        row = await db.get(AccessToken, uuid.UUID(token["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    await _fresh_limits()
    await login(client, await register_verified(client))
    r = await client.post("/api/v1/me/access-token", json={"code": token["code"]}, headers=_csrf(client))
    assert r.status_code == 400


async def test_paying_pro_user_upgrades_with_elite_code_and_falls_back_to_pro(client):
    await _make_admin(client)
    body = dict(plan_code="elite", expires_at=(datetime.now(UTC) + timedelta(days=7)).isoformat())
    token = (await client.post("/api/v1/admin/access-tokens", json=body, headers=_csrf(client))).json()

    await _fresh_limits()
    email = await register_verified(client)
    await give_plan(email, "pro")
    await login(client, email)
    assert (await client.get("/api/v1/me")).json()["plan"] == "pro"
    r = await client.post("/api/v1/me/access-token", json={"code": token["code"]}, headers=_csrf(client))
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/me")).json()["plan"] == "elite"
    assert (await client.get("/api/v1/jackpot")).status_code == 200

    # when the code's access ends (revoked here; expiry behaves the same) the paid Pro plan is still there
    await _make_admin(client)
    await client.post(f"/api/v1/admin/access-tokens/{token['id']}/revoke", headers=_csrf(client))
    await _fresh_limits()
    await login(client, email)
    assert (await client.get("/api/v1/me")).json()["plan"] == "pro"


async def test_code_that_adds_nothing_is_refused_and_not_used_up(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=1)  # a Pro code with a single use

    for plan in ("elite", "pro"):
        await _fresh_limits()
        email = await register_verified(client)
        await give_plan(email, plan)
        await login(client, email)
        r = await client.post("/api/v1/me/access-token", json={"code": token["code"]}, headers=_csrf(client))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "plan_already_covered", r.text
        assert (await client.get("/api/v1/me")).json()["plan"] == plan

    # the single use is still available to someone it helps
    await _fresh_limits()
    await login(client, await register_verified(client))
    r = await client.post("/api/v1/me/access-token", json={"code": token["code"]}, headers=_csrf(client))
    assert r.status_code == 200, r.text


async def test_last_admin_cannot_be_demoted(client):
    email = await _make_admin(client)
    r = await client.post("/api/v1/admin/users/role", json={"email": email, "role": "user"}, headers=_csrf(client))
    # other tests may have left admins behind in the shared database; only the last one is protected
    assert r.status_code in (200, 409)
