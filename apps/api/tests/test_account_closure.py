from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import AuditLog, Payment, User
from app.services.users import purge_closed_accounts
from tests.helpers import PASSWORD, login, register_verified


def _csrf(client) -> dict:
    return {"x-csrf-token": client.cookies.get("ap_csrf")}


async def _user(email: str) -> User | None:
    async with get_sessionmaker()() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def test_closing_keeps_data_for_the_retention_period_then_erases_it(client):
    email = await register_verified(client)
    await login(client, email)
    r = await client.get("/api/v1/me")
    assert r.json()["account_retention_days"] == get_settings().account_retention_days

    r = await client.delete("/api/v1/me", headers=_csrf(client))
    assert r.status_code == 200, r.text
    assert "erased" in r.json()["message"]

    user = await _user(email)
    assert user is not None and user.is_active is False and user.deleted_at is not None
    days = (user.purge_after - user.deleted_at).days
    assert days == get_settings().account_retention_days

    # signed out, and the password no longer opens the account
    assert (await client.get("/api/v1/me")).status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 403 and "closed" in r.json()["detail"]

    async with get_sessionmaker()() as db:
        db.add(Payment(user_id=user.id, provider="manual", provider_ref=f"t-{user.id}", amount_minor=999,
                       currency="USD", status="succeeded"))
        await db.commit()
        # nothing is erased before purge_after
        assert await purge_closed_accounts(db, now=user.purge_after - timedelta(minutes=1)) == 0
    assert await _user(email) is not None

    async with get_sessionmaker()() as db:
        assert await purge_closed_accounts(db, now=user.purge_after + timedelta(minutes=1)) == 1
    assert await _user(email) is None
    async with get_sessionmaker()() as db:
        pay = (await db.execute(select(Payment).where(Payment.provider_ref == f"t-{user.id}"))).scalar_one()
        assert pay.user_id is None and pay.amount_minor == 999  # kept for accounting, without the identity
        closed = (await db.execute(select(AuditLog).where(AuditLog.action == "account_closed"))).scalars().all()
        assert closed


async def test_purge_ignores_active_accounts(client):
    email = await register_verified(client)
    async with get_sessionmaker()() as db:
        assert await purge_closed_accounts(db, now=datetime.now(UTC) + timedelta(days=3650)) == 0
    assert await _user(email) is not None
