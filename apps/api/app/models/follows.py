"""What a user follows: single matches (by prediction_id) and whole leagues (by league_code). Used for the
"My matches" filter and notifications on the site; erased with the account (ON DELETE CASCADE)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import utcnow

FOLLOW_KINDS = ("match", "league")


class UserFollow(Base):
    __tablename__ = "user_follows"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)      # match | league
    target: Mapped[str] = mapped_column(String(64), primary_key=True)   # prediction_id | league_code
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
