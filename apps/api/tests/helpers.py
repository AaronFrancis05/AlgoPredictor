import re
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Subscription, User
from app.services import email as mail

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


async def give_plan(email: str, plan: str) -> None:
    async with get_sessionmaker()() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        db.add(Subscription(user_id=user.id, plan_code=plan, provider="manual", status="active",
                            current_period_end=datetime.now(UTC) + timedelta(days=30)))
        await db.commit()
