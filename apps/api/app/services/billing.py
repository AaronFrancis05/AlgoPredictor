"""Subscriptions with Stripe (cards worldwide) and Flutterwave (African cards + mobile money).

Webhooks are verified, stored once in webhook_events (idempotency) and then applied.
Stripe calls use the StripeClient API of stripe-python 15.x (checked against the installed package).
Flutterwave calls use its v3 REST API; confirm payloads against the current Flutterwave docs before go-live.
"""
import secrets
from datetime import UTC, datetime

import httpx
import stripe
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Payment, Price, Subscription, User, WebhookEvent
from app.services.entitlements import ZERO_DECIMAL_CURRENCIES, forget_user_plans, major_units

log = get_logger(__name__)
FLW_BASE = "https://api.flutterwave.com/v3"
STRIPE_STATUS = {"active": "active", "trialing": "trialing", "past_due": "past_due", "unpaid": "past_due",
                 "canceled": "canceled", "incomplete": "incomplete", "incomplete_expired": "canceled",
                 "paused": "past_due"}


def stripe_client() -> stripe.StripeClient:
    key = get_settings().stripe_secret_key.get_secret_value()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Card payments are not configured")
    return stripe.StripeClient(key)


async def find_price(db: AsyncSession, plan_code: str, currency: str, interval: str) -> Price:
    price = (await db.execute(select(Price).where(Price.plan_code == plan_code, Price.currency == currency,
                                                  Price.interval == interval, Price.is_active.is_(True)))
             ).scalar_one_or_none()
    if price is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This plan is not sold in that currency/interval")
    return price


# ------------------------------------------------------------------------------------------------ Stripe
async def stripe_checkout(db: AsyncSession, user: User, price: Price) -> str:
    if not price.stripe_price_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card payment is not available for this price")
    client = stripe_client()
    s = get_settings()
    if not user.stripe_customer_id:
        customer = await client.v1.customers.create_async(params={"email": user.email,
                                                                  "metadata": {"user_id": str(user.id)}})
        user.stripe_customer_id = customer.id
        await db.commit()
    session = await client.v1.checkout.sessions.create_async(params={
        "mode": "subscription",
        "customer": user.stripe_customer_id,
        "line_items": [{"price": price.stripe_price_id, "quantity": 1}],
        "client_reference_id": str(user.id),
        "subscription_data": {"metadata": {"user_id": str(user.id), "plan_code": price.plan_code}},
        "success_url": f"{s.public_web_url}/account/billing?checkout=success",
        "cancel_url": f"{s.public_web_url}/pricing?checkout=cancelled",
        "allow_promotion_codes": True,
        "automatic_tax": {"enabled": False},
    })
    return session.url


async def stripe_portal(user: User) -> str:
    if not user.stripe_customer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No card subscription on this account")
    session = await stripe_client().v1.billing_portal.sessions.create_async(params={
        "customer": user.stripe_customer_id,
        "return_url": f"{get_settings().public_web_url}/account/billing"})
    return session.url


def verify_stripe_event(payload: bytes, signature: str | None) -> dict:
    secret = get_settings().stripe_webhook_secret.get_secret_value()
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe webhooks are not configured")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from e
    return event.to_dict()


def _period_end(sub: dict) -> datetime | None:
    ts = sub.get("current_period_end")
    if ts is None:  # newer API versions keep the period on the subscription items
        items = (sub.get("items") or {}).get("data") or []
        ts = items[0].get("current_period_end") if items else None
    return datetime.fromtimestamp(ts, UTC) if ts else None


async def apply_stripe_event(db: AsyncSession, event: dict) -> None:
    etype = event["type"]
    obj = event["data"]["object"]
    if etype.startswith("customer.subscription."):
        meta = obj.get("metadata") or {}
        user_id, plan_code = meta.get("user_id"), meta.get("plan_code")
        if not user_id or not plan_code:
            log.warning("stripe_subscription_without_metadata", id=obj.get("id"))
            return
        row = (await db.execute(select(Subscription).where(Subscription.provider_subscription_id == obj["id"]))
               ).scalar_one_or_none()
        if row is None:
            import uuid
            row = Subscription(user_id=uuid.UUID(user_id), plan_code=plan_code, provider="stripe",
                               provider_subscription_id=obj["id"], status="incomplete")
            db.add(row)
        row.plan_code = plan_code
        row.status = "canceled" if etype.endswith("deleted") else STRIPE_STATUS.get(obj.get("status"), "incomplete")
        row.current_period_end = _period_end(obj)
        row.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    elif etype == "invoice.paid":
        user = (await db.execute(select(User).where(User.stripe_customer_id == obj.get("customer")))
                ).scalar_one_or_none()
        await _record_payment(db, user.id if user else None, "stripe", obj["id"], obj.get("amount_paid", 0),
                              (obj.get("currency") or "usd").upper(), "succeeded")


# ------------------------------------------------------------------------------------------------ Flutterwave
def _flw_headers() -> dict:
    key = get_settings().flutterwave_secret_key.get_secret_value()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Mobile money payments are not configured")
    return {"Authorization": f"Bearer {key}"}


async def flutterwave_checkout(db: AsyncSession, user: User, price: Price) -> str:
    if not price.flutterwave_plan_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mobile money is not available for this price")
    s = get_settings()
    tx_ref = f"ap-{user.id}-{price.plan_code}-{secrets.token_hex(6)}"
    body = {
        "tx_ref": tx_ref,
        "amount": major_units(price.amount_minor, price.currency),
        "currency": price.currency,
        "payment_plan": price.flutterwave_plan_id,
        "redirect_url": f"{s.public_web_url}/account/billing?checkout=processing",
        "customer": {"email": user.email, "name": user.full_name or user.email},
        "meta": {"user_id": str(user.id), "plan_code": price.plan_code},
        "customizations": {"title": "AlgoPredict subscription"},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{FLW_BASE}/payments", json=body, headers=_flw_headers())
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or data.get("status") != "success":
        log.error("flutterwave_checkout_failed", status=r.status_code, message=data.get("message"))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Payment provider error, please try again")
    return data["data"]["link"]


def verify_flutterwave_hash(header: str | None) -> None:
    import hmac
    expected = get_settings().flutterwave_webhook_hash.get_secret_value()
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Flutterwave webhooks are not configured")
    if not header or not hmac.compare_digest(header, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")


async def apply_flutterwave_event(db: AsyncSession, event: dict) -> None:
    """charge.completed -> re-verify the transaction with Flutterwave before granting anything."""
    import uuid
    etype = event.get("event") or event.get("event.type") or ""
    data = event.get("data") or {}
    if etype == "charge.completed" and data.get("status") == "successful":
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{FLW_BASE}/transactions/{int(data['id'])}/verify", headers=_flw_headers())
        tx = (r.json() or {}).get("data") or {}
        meta = tx.get("meta") or {}
        if tx.get("status") != "successful" or tx.get("tx_ref") != data.get("tx_ref"):
            log.warning("flutterwave_verify_mismatch", id=data.get("id"))
            return
        user_id, plan_code = meta.get("user_id"), meta.get("plan_code")
        price = (await db.execute(select(Price).where(Price.plan_code == plan_code,
                                                      Price.currency == tx.get("currency"))).scalars().first())
        if price is None or not user_id:
            log.warning("flutterwave_unknown_plan", plan=plan_code)
            return
        expected = major_units(price.amount_minor, price.currency)
        if float(tx.get("amount", 0)) + 1e-9 < float(expected):
            log.warning("flutterwave_underpaid", id=data.get("id"))
            return
        from datetime import timedelta
        days = 366 if price.interval == "year" else 31
        uid = uuid.UUID(user_id)
        row = (await db.execute(select(Subscription).where(Subscription.user_id == uid,
                                                           Subscription.provider == "flutterwave",
                                                           Subscription.plan_code == plan_code))).scalars().first()
        now = datetime.now(UTC)
        if row is None:
            row = Subscription(user_id=uid, plan_code=plan_code, provider="flutterwave", status="active")
            db.add(row)
        end = row.current_period_end
        end = end.replace(tzinfo=UTC) if end is not None and end.tzinfo is None else end
        start = end if end and end > now else now  # renewals extend from the current period end
        row.status, row.current_period_end = "active", start + timedelta(days=days)
        await _record_payment(db, uid, "flutterwave", str(data["id"]), int(round(float(tx["amount"]) * (
            1 if price.currency in ZERO_DECIMAL_CURRENCIES else 100))), tx["currency"], "succeeded")
    elif etype == "subscription.cancelled":
        email = ((data.get("customer") or {}).get("email") or "").lower()
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user:
            for row in (await db.execute(select(Subscription).where(Subscription.user_id == user.id,
                                                                    Subscription.provider == "flutterwave"))).scalars():
                row.cancel_at_period_end = True  # access continues until current_period_end


async def _record_payment(db: AsyncSession, user_id, provider: str, ref: str, amount_minor: int, currency: str,
                          status_: str) -> None:
    exists = (await db.execute(select(Payment).where(Payment.provider == provider, Payment.provider_ref == ref))
              ).scalar_one_or_none()
    if exists is None:
        db.add(Payment(user_id=user_id, provider=provider, provider_ref=ref, amount_minor=amount_minor,
                       currency=currency, status=status_))


async def store_event(db: AsyncSession, provider: str, event_id: str, event_type: str, payload: dict) -> bool:
    """Returns False if this event was already received (duplicate delivery)."""
    db.add(WebhookEvent(provider=provider, event_id=event_id, event_type=event_type, payload=payload))
    try:
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def process_event(db: AsyncSession, provider: str, event_id: str) -> None:
    row = (await db.execute(select(WebhookEvent).where(WebhookEvent.provider == provider,
                                                       WebhookEvent.event_id == event_id))).scalar_one()
    if row.processed_at is not None:
        return
    try:
        if provider == "stripe":
            await apply_stripe_event(db, row.payload)
        else:
            await apply_flutterwave_event(db, row.payload)
        row.processed_at, row.error = datetime.now(UTC), None
    except Exception as e:  # keep the event for retry, record the error
        await db.rollback()
        row = (await db.execute(select(WebhookEvent).where(WebhookEvent.provider == provider,
                                                           WebhookEvent.event_id == event_id))).scalar_one()
        row.error = f"{e.__class__.__name__}: {e}"[:2000]
        log.error("webhook_processing_failed", provider=provider, event_id=event_id, error=row.error)
    await db.commit()
    await forget_user_plans()  # a subscription may have changed: no one waits for the plan cache to expire
