import hashlib
import hmac
import json
import time
import uuid

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import User, WebhookEvent
from tests.helpers import login, register_verified

STRIPE_SECRET = "whsec_test_secret"


def stripe_headers(payload: bytes) -> dict:
    """Signature in Stripe's documented scheme: v1 = HMAC-SHA256(secret, "<t>.<payload>")."""
    t = str(int(time.time()))
    sig = hmac.new(STRIPE_SECRET.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"}


async def test_plans_listed_with_prices(client):
    plans = (await client.get("/api/v1/plans")).json()
    assert [p["code"] for p in plans] == ["free", "pro", "elite"]
    pro = plans[1]
    assert any(x["currency"] == "USD" and x["amount_minor"] == 999 for x in pro["prices"])


async def test_stripe_webhook_creates_subscription_idempotently(client):
    email = await register_verified(client)
    async with get_sessionmaker()() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    sub_id = f"sub_{uuid.uuid4().hex[:10]}"
    event = {"id": f"evt_{uuid.uuid4().hex[:10]}", "object": "event", "type": "customer.subscription.created",
             "data": {"object": {"id": sub_id, "object": "subscription", "status": "active",
                                 "cancel_at_period_end": False, "current_period_end": int(time.time()) + 86400 * 30,
                                 "metadata": {"user_id": str(user.id), "plan_code": "elite"}}}}
    payload = json.dumps(event).encode()
    r = await client.post("/webhooks/stripe", content=payload, headers=stripe_headers(payload))
    assert r.status_code == 200, r.text
    r = await client.post("/webhooks/stripe", content=payload, headers=stripe_headers(payload))
    assert r.status_code == 200
    async with get_sessionmaker()() as db:
        n = len((await db.execute(select(WebhookEvent).where(WebhookEvent.event_id == event["id"]))).all())
    assert n == 1
    me = (await login(client, email))["user"]
    assert me["plan"] == "elite" and me["entitlements"]["jackpot"] is True


async def test_stripe_webhook_rejects_bad_signature(client):
    payload = b'{"id": "evt_x", "type": "customer.subscription.created"}'
    r = await client.post("/webhooks/stripe", content=payload,
                          headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"})
    assert r.status_code == 400


async def test_flutterwave_webhook_requires_hash(client):
    r = await client.post("/webhooks/flutterwave", json={"event": "charge.completed", "data": {"id": 1}},
                          headers={"verif-hash": "wrong"})
    assert r.status_code == 401


async def test_checkout_without_provider_keys_is_503(client):
    email = await register_verified(client)
    data = await login(client, email)
    r = await client.post("/api/v1/billing/checkout", headers={"x-csrf-token": data["csrf_token"]},
                          json={"plan_code": "pro", "currency": "usd", "interval": "month", "provider": "stripe"})
    assert r.status_code in (404, 503)  # no stripe_price_id configured in tests
