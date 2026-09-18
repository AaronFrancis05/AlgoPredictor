import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import Timestamps, UUIDPk, utcnow


class Plan(Base):
    """free / pro / elite. `entitlements` is editable data, not code (see services/entitlements.py)."""
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    rank: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    entitlements: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Price(UUIDPk, Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("plan_code", "currency", "interval"),)

    plan_code: Mapped[str] = mapped_column(String(20), ForeignKey("plans.code"), index=True)
    currency: Mapped[str] = mapped_column(String(3))             # ISO 4217, upper case
    interval: Mapped[str] = mapped_column(String(10))            # month | year
    amount_minor: Mapped[int] = mapped_column(Integer)           # cents; UGX has no minor unit (stored as-is)
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))
    flutterwave_plan_id: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccessToken(UUIDPk, Base):
    """An admin-issued code that grants a paid plan until expires_at. Only the SHA-256 digest is stored; the code
    is shown once at creation. Each redemption is a Subscription (provider "access_token") pointing back here."""
    __tablename__ = "access_tokens"

    code_digest: Mapped[str] = mapped_column(String(64), unique=True)
    code_hint: Mapped[str] = mapped_column(String(12))            # first characters, to recognise it in lists
    plan_code: Mapped[str] = mapped_column(String(20), ForeignKey("plans.code"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_redemptions: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    note: Mapped[str] = mapped_column(String(120), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subscription(UUIDPk, Timestamps, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_user_status", "user_id", "status"),  # active_plan lookup
                      UniqueConstraint("access_token_id", "user_id"))            # one redemption per person

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_code: Mapped[str] = mapped_column(String(20), ForeignKey("plans.code"))
    provider: Mapped[str] = mapped_column(String(20))            # stripe | flutterwave | manual | access_token
    access_token_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("access_tokens.id", ondelete="SET NULL"), index=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # active | trialing | past_due | canceled | incomplete
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(UUIDPk, Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "provider_ref"),)

    # indexed so erasing a user (ON DELETE SET NULL) and the data export do not scan every payment
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str] = mapped_column(String(128))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(UUIDPk, Base):
    """Every provider event is stored once (idempotency) before it is processed."""
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),
                      # the worker polls unprocessed events every 5 minutes
                      Index("ix_webhook_events_pending", "received_at",
                            postgresql_where=text("processed_at IS NULL")))

    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
