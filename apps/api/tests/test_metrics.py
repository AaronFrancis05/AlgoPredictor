"""/metrics lists every route with its traffic, so it is private: absent without METRICS_TOKEN, bearer-only with it."""
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app

TOKEN = "m" * 40


async def test_metrics_absent_without_token(client):
    assert (await client.get("/metrics")).status_code == 404


async def test_metrics_needs_the_bearer_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_token", type(get_settings().metrics_token)(TOKEN))
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        assert (await c.get("/metrics")).status_code == 404
        assert (await c.get("/metrics", headers={"authorization": "Bearer wrong"})).status_code == 404
        r = await c.get("/metrics", headers={"authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200 and "http_request" in r.text
