"""Live match state from a live-score feed. Display only: grading still comes from the pipeline's review.py.

A match is keyed like the pipeline keys it (kick-off date, home team, away team). Picks stay append-only; the
changing state lives here.
"""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models._common import utcnow


class LiveMatch(Base):
    __tablename__ = "live_matches"

    match_key: Mapped[str] = mapped_column(String(200), primary_key=True)    # "YYYY-MM-DD|home|away"
    kickoff_date: Mapped[date] = mapped_column(Date, index=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    league_code: Mapped[str] = mapped_column(String(8))
    home_team: Mapped[str] = mapped_column(String(80))
    away_team: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(20), default="")
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    link_method: Mapped[str] = mapped_column(String(16), default="")         # exact | one_side | admin
    candidates: Mapped[list] = mapped_column(JSON, default=list)              # feed fixtures at this kick-off
    status: Mapped[str] = mapped_column(String(8), default="")               # provider short code (1H, HT, FT...)
    elapsed: Mapped[int | None] = mapped_column(Integer)
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # last score update
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LiveTeamAlias(Base):
    """A feed's name for a club -> the dataset's name. Only written when an admin confirms a link."""
    __tablename__ = "live_team_aliases"

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(120), primary_key=True)  # normalised
    team: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
