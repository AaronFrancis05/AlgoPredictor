import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.db.session import get_sessionmaker
from app.models import Subscription, User, UserNotification
from app.services import notifications
from tests.helpers import login, register_verified
from tests.test_access_tokens import _create_token, _csrf, _fresh_limits, _make_admin


async def _redeem(client, code: str) -> str:
    """Sign in a new user and redeem `code`; returns the user's email."""
    await _fresh_limits()
    email = await register_verified(client)
    await login(client, email)
    r = await client.post("/api/v1/me/access-token", json={"code": code}, headers=_csrf(client))
    assert r.status_code == 200, r.text
    return email


async def _inbox(client) -> dict:
    r = await client.get("/api/v1/me/notifications")
    assert r.status_code == 200, r.text
    return r.json()


async def test_redeeming_a_code_notifies_and_read_marks_clear_it(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=5)
    await _redeem(client, token["code"])

    inbox = await _inbox(client)
    assert inbox["unread"] == 1
    [n] = inbox["items"]
    assert n["kind"] == "access_granted" and n["read"] is False and n["link"] == "/dashboard"
    assert "Pro plan unlocked" in n["title"] and "until" in n["body"]

    r = await client.post("/api/v1/me/notifications/read", json={}, headers=_csrf(client))
    assert r.status_code == 422  # neither ids nor all
    r = await client.post("/api/v1/me/notifications/read", json={"ids": [n["id"]]}, headers=_csrf(client))
    assert r.status_code == 200 and r.json()["unread"] == 0 and r.json()["items"][0]["read"] is True


async def test_notifications_are_private(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=5)
    await _redeem(client, token["code"])
    theirs = (await _inbox(client))["items"][0]["id"]

    await _fresh_limits()
    await login(client, await register_verified(client))
    assert (await _inbox(client)) == {"items": [], "unread": 0}
    r = await client.post("/api/v1/me/notifications/read", json={"ids": [theirs]}, headers=_csrf(client))
    assert r.status_code == 200
    async with get_sessionmaker()() as db:  # someone else's id changed nothing
        row = await db.get(UserNotification, uuid.UUID(theirs))
        assert row.read_at is None


async def test_revoking_a_code_tells_its_users(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=5)
    email = await _redeem(client, token["code"])

    await _make_admin(client)
    assert (await client.post(f"/api/v1/admin/access-tokens/{token['id']}/revoke",
                              headers=_csrf(client))).status_code == 200
    await _fresh_limits()
    await login(client, email)
    inbox = await _inbox(client)
    assert inbox["unread"] == 2
    ended = inbox["items"][0]
    assert ended["kind"] == "access_ended" and "withdrawn" in ended["body"] and ended["link"] == "/account/plans"


async def test_reminder_before_and_after_access_ends_is_sent_once(client):
    await _make_admin(client)
    body = dict(plan_code="elite", expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat(), max_redemptions=5)
    token = (await client.post("/api/v1/admin/access-tokens", json=body, headers=_csrf(client))).json()
    email = await _redeem(client, token["code"])

    async with get_sessionmaker()() as db:
        user_id = (await db.execute(select(User.id).where(User.email == email))).scalar_one()
        assert await notifications.access_reminders(db) >= 1
        await notifications.access_reminders(db)  # a second run adds nothing for this user
        kinds = (await db.execute(select(UserNotification.kind).where(UserNotification.user_id == user_id))).scalars()
        assert sorted(kinds) == ["access_ending", "access_granted"]

        # the access period passes: one "ended" message, however often the job runs
        await db.execute(update(Subscription).where(Subscription.user_id == user_id)
                         .values(current_period_end=datetime.now(UTC) - timedelta(minutes=5)))
        await db.commit()
        await notifications.access_reminders(db)
        await notifications.access_reminders(db)
        kinds = (await db.execute(select(UserNotification.kind).where(UserNotification.user_id == user_id))).scalars()
        assert sorted(kinds) == ["access_ended", "access_ending", "access_granted"]

    await _fresh_limits()
    await login(client, email)
    inbox = await _inbox(client)
    assert inbox["items"][0]["kind"] == "access_ended" and "is over" in inbox["items"][0]["body"]


async def test_old_notifications_are_purged(client):
    await _make_admin(client)
    token = await _create_token(client, max_redemptions=5)
    email = await _redeem(client, token["code"])
    async with get_sessionmaker()() as db:
        user_id = (await db.execute(select(User.id).where(User.email == email))).scalar_one()
        await db.execute(update(UserNotification).where(UserNotification.user_id == user_id)
                         .values(created_at=datetime.now(UTC) - timedelta(days=notifications.KEEP_DAYS + 1)))
        await db.commit()
        assert await notifications.purge_old(db) >= 1
    assert (await _inbox(client))["items"] == []
