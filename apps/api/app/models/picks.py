"""Predictions published by the ML pipeline (parent project predict.py / review.py). Append-only."""
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import UUIDPk, utcnow


class Pick(Base):
    __tablename__ = "picks"
    __table_args__ = (Index("ix_picks_day_conf", "kickoff_date", "confidence"),)

    prediction_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(40))
    made_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kickoff_date: Mapped[date] = mapped_column(Date, index=True)          # UK local date (football-data)
    kickoff_time: Mapped[str] = mapped_column(String(5), default="")      # UK local HH:MM, may be empty
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # UTC
    league_code: Mapped[str] = mapped_column(String(8), index=True)
    home_team: Mapped[str] = mapped_column(String(80))
    away_team: Mapped[str] = mapped_column(String(80))
    p_home: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away: Mapped[float] = mapped_column(Float)
    pick: Mapped[str] = mapped_column(String(5))                          # home | draw | away
    confidence: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String(8))
    odds_used: Mapped[float | None] = mapped_column(Float)
    odds_source: Mapped[str] = mapped_column(String(60), default="")
    edge: Mapped[float | None] = mapped_column(Float)
    value_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[str] = mapped_column(String(200), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PickResult(Base):
    __tablename__ = "pick_results"

    prediction_id: Mapped[str] = mapped_column(String(40), ForeignKey("picks.prediction_id", ondelete="CASCADE"),
                                               primary_key=True)
    result: Mapped[str] = mapped_column(String(5))
    correct: Mapped[bool] = mapped_column(Boolean)
    rps: Mapped[float] = mapped_column(Float)
    profit: Mapped[float | None] = mapped_column(Float)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Slip(UUIDPk, Base):
    """A target-odds slip generated for a user (kept for quotas and history)."""
    __tablename__ = "slips"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))            # target_odds | jackpot | top10
    target_odds: Mapped[float | None] = mapped_column(Float)
    combined_odds: Mapped[float | None] = mapped_column(Float)
    combined_probability: Mapped[float | None] = mapped_column(Float)
    legs: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
