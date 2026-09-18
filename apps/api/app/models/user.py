import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import Timestamps, UUIDPk, utcnow

ROLE_USER, ROLE_ADMIN = "user", "admin"
ROLES = (ROLE_USER, ROLE_ADMIN)


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_purge_after", "purge_after", postgresql_where=text("purge_after IS NOT NULL")),)

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))       # None for Google-only accounts
    full_name: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str | None] = mapped_column(String(2))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    age_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # "user" | "admin". Admins get every plan feature without paying and the /admin endpoints.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    api_key_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Account closure: the account is disabled at deleted_at and its row is erased at purge_after
    # (ACCOUNT_RETENTION_DAYS later) by the worker. Payment and audit rows outlive it without the link.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Two-factor sign-in (TOTP). The secret is Fernet-encrypted; it is pending until totp_enabled_at is set.
    # totp_last_step makes every code single-use; recovery codes are stored as SHA-256 digests.
    totp_secret_enc: Mapped[str | None] = mapped_column(String(255))
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    mfa_recovery_digests: Mapped[list | None] = mapped_column(JSON)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def mfa_enabled(self) -> bool:
        return self.totp_enabled_at is not None


class OAuthAccount(UUIDPk, Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(UUIDPk, Base):
    """Rotating refresh tokens. A token reused after rotation revokes its whole family."""
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    # the session was started with a second factor; carried through every rotation of the family
    mfa: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailToken(UUIDPk, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))            # verify | reset
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
