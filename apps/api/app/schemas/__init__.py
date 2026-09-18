"""Pydantic v2 request/response models."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN = 10


class Message(BaseModel):
    message: str


# ---------------------------------------------------------------- auth / users
def _strong_password(v: str) -> str:
    classes = sum([any(c.islower() for c in v), any(c.isupper() for c in v), any(c.isdigit() for c in v),
                   any(not c.isalnum() for c in v)])
    if classes < 3:
        raise ValueError("use at least three of: lower case, upper case, digits, symbols")
    return v


def _must_be_true(v: bool) -> bool:
    if not v:
        raise ValueError("required")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    full_name: str = Field(default="", max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    confirm_age_18: bool
    accept_terms: bool

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _strong_password(v)

    @field_validator("confirm_age_18", "accept_terms")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        return _must_be_true(v)

    @field_validator("country")
    @classmethod
    def upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class PasswordResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _strong_password(v)


class PasswordSetIn(BaseModel):
    """Set a first password (Google-only account) or change it. Changing needs the current password."""
    current_password: str | None = Field(default=None, max_length=128)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _strong_password(v)


class GoogleLinkOut(BaseModel):
    url: str


class AgeConfirmIn(BaseModel):
    confirm_age_18: bool

    @field_validator("confirm_age_18")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        return _must_be_true(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    country: str | None
    email_verified: bool
    age_confirmed: bool
    is_admin: bool
    plan: str
    entitlements: dict
    has_api_key: bool
    has_password: bool
    google_linked: bool


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str
    access_token_expires_in: int


class ApiKeyOut(BaseModel):
    api_key: str
    note: str = "Shown once. Store it securely; send it in the X-API-Key header."


# ---------------------------------------------------------------- picks
PickSide = Literal["home", "draw", "away"]


class PickOut(BaseModel):
    prediction_id: str
    kickoff_date: date
    kickoff_time: str
    kickoff_at: datetime
    league_code: str
    home_team: str
    away_team: str
    pick: PickSide | None                # None while hidden for the free plan
    confidence: float | None
    tier: str
    tier_hit_rate: float | None
    p_home: float | None
    p_draw: float | None
    p_away: float | None
    fair_odds: float | None
    odds: float | None
    edge: float | None
    value_flag: bool | None              # None unless the plan includes VALUE flags
    locked: bool = False
    is_demo: bool = False
    model_version: str
    result: PickSide | None = None
    correct: bool | None = None


class PicksDayOut(BaseModel):
    date: date
    plan: str
    picks: list[PickOut]
    total_published: int
    hidden_count: int
    tier_hit_rates: dict[str, float]
    tier_hit_rates_source: str
    disclaimer: str


class SlipIn(BaseModel):
    target_odds: float = Field(ge=1.5, le=200)
    date_from: date | None = None
    date_to: date | None = None
    min_legs: int = Field(default=2, ge=2, le=6)
    max_legs: int = Field(default=6, ge=2, le=6)
    tolerance: float = Field(default=0.15, ge=0.02, le=0.30)
    prefer_value: bool = False

    @field_validator("max_legs")
    @classmethod
    def legs_order(cls, v: int, info) -> int:
        if v < info.data.get("min_legs", 2):
            raise ValueError("max_legs must be >= min_legs")
        return v


class SlipOut(BaseModel):
    found: bool
    target_odds: float
    combined_odds: float | None
    combined_probability: float | None
    expected_value: float | None
    legs: list[PickOut]
    message: str
    remaining_today: int | None


class JackpotDayOut(BaseModel):
    date: date
    legs: list[PickOut]
    combined_probability: float | None
    complete: bool


class JackpotOut(BaseModel):
    week_start: date
    days: list[JackpotDayOut]
    complete: bool
    week_combined_probability: float | None
    note: str


class TrackRecordOut(BaseModel):
    graded: int
    hit_rate: float | None
    mean_rps: float | None
    by_tier: list[dict]
    by_month: list[dict]
    recent: list[PickOut]
    live_since: date | None
    backtest: dict


# ---------------------------------------------------------------- billing
class PriceOut(BaseModel):
    currency: str
    interval: Literal["month", "year"]
    amount_minor: int
    providers: list[str]


class PlanOut(BaseModel):
    code: str
    name: str
    rank: int
    description: str
    entitlements: dict
    prices: list[PriceOut]


class CheckoutIn(BaseModel):
    plan_code: Literal["pro", "elite"]
    currency: str = Field(min_length=3, max_length=3)
    interval: Literal["month", "year"] = "month"
    provider: Literal["stripe", "flutterwave"]

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class RedirectOut(BaseModel):
    url: str


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_code: str
    provider: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool


# ---------------------------------------------------------------- ingest
class IngestPick(BaseModel):
    prediction_id: str = Field(min_length=4, max_length=40)
    made_at: datetime
    model_version: str = Field(max_length=40)
    date: date
    time: str = Field(default="", max_length=5)
    league_code: str = Field(max_length=8)
    home_team: str = Field(max_length=80)
    away_team: str = Field(max_length=80)
    p_home: float = Field(ge=0, le=1)
    p_draw: float = Field(ge=0, le=1)
    p_away: float = Field(ge=0, le=1)
    pick: PickSide
    confidence: float = Field(ge=0, le=1)
    tier: Literal["Strong", "Medium", "Lean"]
    odds_used: float | None = Field(default=None, gt=1)
    odds_source: str = Field(default="", max_length=60)
    edge: float | None = None
    value_flag: str | bool | None = ""
    flags: str | None = Field(default="", max_length=200)
    is_demo: bool = False


class IngestResult(BaseModel):
    prediction_id: str = Field(min_length=4, max_length=40)
    result: PickSide
    correct: bool
    rps: float = Field(ge=0, le=1)
    profit: float | None = None


class IngestPicksIn(BaseModel):
    picks: list[IngestPick] = Field(max_length=5000)


class IngestResultsIn(BaseModel):
    results: list[IngestResult] = Field(max_length=20000)


class IngestOut(BaseModel):
    received: int
    inserted: int
    skipped_existing: int
