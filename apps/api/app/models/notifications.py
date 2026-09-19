"""In-app notifications: messages for one user (plan changes, access codes, reminders), shown under the bell in
the site header and, when the user allows it, as device notifications. Erased with the account (ON DELETE CASCADE)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import UUIDPk, utcnow


class UserNotification(UUIDPk, Base):
    __tablename__ = "user_notifications"
    __table_args__ = (Index("ix_user_notifications_user_created", "user_id", "created_at"),
                      # one notification per event, so retries and repeated jobs never send it twice
                      UniqueConstraint("user_id", "dedupe_key"))

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))            # access_granted | access_ending | access_ended | ...
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(500), default="")
    link: Mapped[str | None] = mapped_column(String(200))    # site path to open, e.g. /account
    dedupe_key: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
