import re
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Subscription, User
from app.services import email as mail
from app.services.entitlements import forget_user_plans

PASSWORD = "Str0ng-password!"


async def register_verified(client: AsyncClient, email: str | None = None) -> str:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/v1/auth/register", json=dict(email=email, password=PASSWORD, full_name="Test",
                                                             confirm_age_18=True, accept_terms=True))
    assert r.status_code == 201, r.text
    body = mail.OUTBOX[-1].get_content()
    token = re.search(r"token=([\w\-]+)", body).group(1)
    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    return email


async def login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


async def reset_rate_limits() -> None:
    """Clear only the rate-limit windows (keeps two-factor challenges and failure counters)."""
    from app.core.redis import get_redis
    redis = get_redis()
    keys = await redis.keys("rl:*")
    if keys:
        await redis.delete(*keys)


def csrf(client: AsyncClient) -> dict:
    return {"x-csrf-token": client.cookies.get("ap_csrf")}


def totp_code(secret: str, steps_ahead: int = 0) -> str:
    """A valid code. Each code works once, so a second code in the same 30 s uses the next step (still in window)."""
    from app.core import totp
    return totp.code_at(secret, totp.current_step() + steps_ahead)


async def enable_mfa(client: AsyncClient, password: str | None = PASSWORD) -> tuple[str, list[str]]:
    """Turn on two-factor for the signed-in user; returns (secret, recovery codes). The session becomes mfa=True."""
    r = await client.post("/api/v1/me/mfa/setup", headers=csrf(client))
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = await client.post("/api/v1/me/mfa/enable", json={"code": totp_code(secret), "current_password": password},
                          headers=csrf(client))
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


async def give_plan(email: str, plan: str) -> None:
    async with get_sessionmaker()() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        db.add(Subscription(user_id=user.id, plan_code=plan, provider="manual", status="active",
                            current_period_end=datetime.now(UTC) + timedelta(days=30)))
        await db.commit()
    await forget_user_plans()  # as the billing code does after applying an event
