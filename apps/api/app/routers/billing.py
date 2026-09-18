"""Plans, checkout and webhooks for Stripe and Flutterwave."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.deps import current_user
from app.models import Plan, Price, Subscription, User
from app.schemas import CheckoutIn, PlanOut, PriceOut, RedirectOut, SubscriptionOut
from app.services import billing
from app.services.audit import audit

settings = get_settings()
router = APIRouter(tags=["billing"])
webhooks = APIRouter(prefix="/webhooks", tags=["webhooks"])
checkout_limit = rate_limit("checkout", "10/60")


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(response: Response, db: AsyncSession = Depends(get_db)) -> list[PlanOut]:
    plans = (await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.rank))).scalars().all()
    prices = (await db.execute(select(Price).where(Price.is_active.is_(True)))).scalars().all()
    response.headers["Cache-Control"] = "public, max-age=300"
    out = []
    for p in plans:
        mine = [x for x in prices if x.plan_code == p.code]
        out.append(PlanOut(code=p.code, name=p.name, rank=p.rank, description=p.description,
                           entitlements=p.entitlements,
                           prices=[PriceOut(currency=x.currency, interval=x.interval, amount_minor=x.amount_minor,
                                            providers=[n for n, v in (("stripe", x.stripe_price_id),
                                                                      ("flutterwave", x.flutterwave_plan_id)) if v])
                                   for x in sorted(mine, key=lambda x: (x.currency, x.interval))]))
    return out


@router.get("/billing/subscription", response_model=list[SubscriptionOut])
async def my_subscriptions(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Subscription).where(Subscription.user_id == user.id)
                             .order_by(Subscription.created_at.desc()))).scalars().all()


@router.post("/billing/checkout", response_model=RedirectOut, dependencies=[Depends(checkout_limit)])
async def checkout(body: CheckoutIn, request: Request, user: User = Depends(current_user),
                   db: AsyncSession = Depends(get_db)) -> RedirectOut:
    if user.email_verified_at is None or user.age_confirmed_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "verify_first"})
    price = await billing.find_price(db, body.plan_code, body.currency, body.interval)
    if body.provider == "stripe":
        url = await billing.stripe_checkout(db, user, price)
    else:
        url = await billing.flutterwave_checkout(db, user, price)
    await audit(db, "checkout_started", request, user.id, plan=body.plan_code, provider=body.provider,
                currency=body.currency)
    await db.commit()
    return RedirectOut(url=url)


@router.post("/billing/portal", response_model=RedirectOut)
async def portal(user: User = Depends(current_user)) -> RedirectOut:
    return RedirectOut(url=await billing.stripe_portal(user))


@webhooks.post("/stripe", status_code=200)
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None),
                         db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.body()
    event = billing.verify_stripe_event(payload, stripe_signature)
    if await billing.store_event(db, "stripe", event["id"], event["type"], event):
        await billing.process_event(db, "stripe", event["id"])
    return {"received": True}


@webhooks.post("/flutterwave", status_code=200)
async def flutterwave_webhook(request: Request, verif_hash: str | None = Header(default=None),
                              db: AsyncSession = Depends(get_db)) -> dict:
    billing.verify_flutterwave_hash(verif_hash)
    event = await request.json()
    data = event.get("data") or {}
    event_id = str(data.get("id") or event.get("id") or "")
    if not event_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing event id")
    etype = str(event.get("event") or event.get("event.type") or "unknown")
    if await billing.store_event(db, "flutterwave", f"{etype}:{event_id}", etype, event):
        await billing.process_event(db, "flutterwave", f"{etype}:{event_id}")
    return {"received": True}
