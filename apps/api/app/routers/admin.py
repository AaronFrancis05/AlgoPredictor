"""Admin: platform stats, failed webhooks, roles and access tokens (plan grants). Every route needs role=admin."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import admin_user
from app.models import ROLE_ADMIN, AccessToken, Pick, PickResult, Subscription, User, WebhookEvent
from app.schemas import AccessTokenCreatedOut, AccessTokenIn, AccessTokenOut, Message, RoleIn
from app.services import access_tokens as tokens
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)) -> dict:
    count = lambda q: db.execute(select(func.count()).select_from(q))  # noqa: E731
    return dict(
        users=(await count(User)).scalar_one(),
        active_subscriptions={plan: n for plan, n in (await db.execute(
            select(Subscription.plan_code, func.count()).where(Subscription.status.in_(("active", "trialing")))
            .group_by(Subscription.plan_code))).all()},
        picks=(await count(Pick)).scalar_one(),
        graded=(await count(PickResult)).scalar_one(),
        failed_webhooks=(await db.execute(select(func.count()).select_from(WebhookEvent)
                                          .where(WebhookEvent.error.is_not(None)))).scalar_one(),
    )


@router.get("/webhooks/failed")
async def failed_webhooks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(WebhookEvent).where(WebhookEvent.error.is_not(None))
                             .order_by(WebhookEvent.received_at.desc()).limit(100))).scalars().all()
    return [dict(provider=r.provider, event_id=r.event_id, type=r.event_type, received_at=r.received_at,
                 error=r.error) for r in rows]


# ------------------------------------------------------------------------------------------------ roles
@router.post("/users/role", response_model=Message)
async def set_role(body: RoleIn, request: Request, admin: User = Depends(admin_user),
                   db: AsyncSession = Depends(get_db)) -> Message:
    if body.role != ROLE_ADMIN:
        admins = (await db.execute(select(func.count()).select_from(User).where(User.role == ROLE_ADMIN))).scalar_one()
        target = (await db.execute(select(User.role).where(User.email == body.email.lower()))).scalar_one_or_none()
        if target == ROLE_ADMIN and admins <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Keep at least one admin")
    try:
        user = await tokens.set_role(db, body.email, body.role)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that email") from e
    await audit(db, "role_changed", request, admin.id, target=str(user.id), role=body.role)
    await db.commit()
    await tokens.after_change()
    return Message(message=f"{user.email} is now {body.role}.")


# ------------------------------------------------------------------------------------------------ access tokens
def _out(t: AccessToken, redemptions: int, now: datetime, redeemed_by: list[dict] | None = None) -> dict:
    return dict(id=t.id, code_hint=t.code_hint, plan_code=t.plan_code, expires_at=t.expires_at,
                max_redemptions=t.max_redemptions, redemptions=redemptions, note=t.note,
                status=tokens.token_status(t, now, redemptions), created_at=t.created_at, revoked_at=t.revoked_at,
                redeemed_by=redeemed_by or [])


@router.get("/access-tokens", response_model=list[AccessTokenOut])
async def list_access_tokens(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(AccessToken).order_by(AccessToken.created_at.desc()).limit(200))).scalars().all()
    counts = await tokens.redemption_counts(db, [t.id for t in rows])
    now = datetime.now(UTC)
    return [_out(t, counts.get(t.id, 0), now, await tokens.redeemers(db, t.id)) for t in rows]


@router.post("/access-tokens", response_model=AccessTokenCreatedOut, status_code=201)
async def create_access_token(body: AccessTokenIn, request: Request, admin: User = Depends(admin_user),
                              db: AsyncSession = Depends(get_db)) -> dict:
    token, code = await tokens.create(db, admin, body.plan_code, body.expires_at, body.max_redemptions, body.note)
    await audit(db, "access_token_created", request, admin.id, token=str(token.id), plan=body.plan_code,
                expires_at=body.expires_at.isoformat(), max_redemptions=body.max_redemptions)
    await db.commit()
    return {**_out(token, 0, datetime.now(UTC)), "code": code}


@router.post("/access-tokens/{token_id}/revoke", response_model=AccessTokenOut)
async def revoke_access_token(token_id: UUID, request: Request, admin: User = Depends(admin_user),
                              db: AsyncSession = Depends(get_db)) -> dict:
    token = await tokens.revoke(db, token_id)
    await audit(db, "access_token_revoked", request, admin.id, token=str(token_id))
    await db.commit()
    await tokens.after_change()
    counts = await tokens.redemption_counts(db, [token.id])
    return _out(token, counts.get(token.id, 0), datetime.now(UTC), await tokens.redeemers(db, token.id))
