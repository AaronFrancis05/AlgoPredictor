"""Test setup: SQLite (aiosqlite) + fakeredis. CI also runs the suite against Postgres (DATABASE_URL override)."""
import os
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_db_file}")
os.environ.update({
    "ENVIRONMENT": "test",
    "COOKIE_SECURE": "false",
    "RATE_LIMIT_AUTH": "8/60",
    "RATE_LIMIT_DEFAULT": "1000/60",
    "RATE_LIMIT_PRODUCTS": "1000/60",
    "INGEST_HMAC_SECRET": "test-ingest-secret",
    "STRIPE_WEBHOOK_SECRET": "whsec_test_secret",
    "FLUTTERWAVE_WEBHOOK_HASH": "flw-test-hash",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-123456",
})

import pytest  # noqa: E402
from fakeredis import FakeAsyncRedis  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.redis import set_redis  # noqa: E402
from app.db.session import Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_plans  # noqa: E402
from app.services import email as mail  # noqa: E402

_redis = FakeAsyncRedis(decode_responses=True)
set_redis(_redis)


@pytest.fixture(scope="session", autouse=True)
async def database():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_plans()
    yield


@pytest.fixture(autouse=True)
async def clean_state():
    await _redis.flushall()
    mail.OUTBOX.clear()
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
