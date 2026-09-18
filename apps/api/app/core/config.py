"""Application settings, loaded from environment variables (see .env.example)."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "AlgoPredict"
    api_prefix: str = "/api/v1"
    public_web_url: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "api", "testserver"])
    log_level: str = "INFO"
    trusted_proxy_count: int = 0          # number of reverse proxies whose X-Forwarded-For is trusted
    # Shared with the web server: requests proxied by Next.js carry X-Client-IP + this secret, so the API can
    # rate-limit the real visitor instead of the web server. Empty = header ignored.
    proxy_shared_secret: SecretStr = SecretStr("")

    database_url: str = "postgresql+asyncpg://algopredict:algopredict@localhost:5432/algopredict"
    # Supabase: postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
    db_ssl: Literal["disable", "require", "verify-full"] = "disable"
    db_transaction_pooler: bool = False   # True for the Supabase transaction pooler (port 6543)
    # Upstash: rediss://default:<password>@<name>.upstash.io:6379  (rediss = TLS; Upstash has database 0 only)
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 5.0
    # arq polls Redis every poll_delay seconds; Upstash bills per command, and the worker only runs crons
    worker_poll_delay_seconds: float = 10.0

    # auth
    jwt_secret: SecretStr = SecretStr("change-me-in-production-at-least-32-bytes!!")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_domain: str | None = None
    cookie_secure: bool = True
    max_login_failures: int = 5
    lockout_minutes: int = 15
    email_token_hours: int = 24
    # Closed accounts are disabled at once and erased this many days later (restorable by support until then).
    # Set it to the period your legal advice requires. Payment records are kept separately, without the identity.
    account_retention_days: int = Field(default=30, ge=0, le=3650)

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    # ingest from the ML pipeline (HMAC-SHA256)
    ingest_hmac_secret: SecretStr = SecretStr("change-me-ingest-secret")
    ingest_max_skew_seconds: int = 300
    web_revalidate_url: str = ""          # e.g. http://web:3000/api/revalidate
    web_revalidate_secret: SecretStr = SecretStr("")

    # billing
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_webhook_secret: SecretStr = SecretStr("")
    flutterwave_secret_key: SecretStr = SecretStr("")
    flutterwave_webhook_hash: SecretStr = SecretStr("")

    # email: Resend's HTTPS API when RESEND_API_KEY is set (Railway blocks outbound SMTP on trial/Hobby),
    # otherwise SMTP (Mailpit locally). SMTP_FROM is the sender for both and must be on a Resend-verified domain.
    resend_api_key: SecretStr = SecretStr("")
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "AlgoPredict <no-reply@algopredict.local>"

    # rate limits: "<count>/<seconds>"
    rate_limit_default: str = "120/60"
    rate_limit_auth: str = "5/60"
    rate_limit_products: str = "30/60"

    # live scores (display only: never used for grading or by the model). API-Football (api-sports.io);
    # empty key = no live feed, matches still move to Live / History by kick-off time and the official result.
    api_football_key: SecretStr = SecretStr("")
    api_football_url: str = "https://v3.football.api-sports.io"
    livescore_daily_budget: int = Field(default=100, ge=0)   # provider requests per UTC day (free plan: 100)
    livescore_reserve: int = Field(default=5, ge=0)           # kept back for fixture-list syncs and admin use
    livescore_min_interval_seconds: int = Field(default=60, ge=15)
    # a match with no feed counts as in play for this long after kick-off, then "awaiting result"
    match_live_minutes: int = Field(default=115, ge=90, le=180)

    # measured walk-forward hit rates of the current champion (reports/train_20260917_0847.md).
    # Only the hit rates and the match count are public; model name, method and RPS stay internal.
    tier_hit_rates: dict[str, float] = Field(
        default_factory=lambda: {"Strong": 0.745, "Medium": 0.570, "Lean": 0.419})
    backtest_matches: int = 38732

    @property
    def tier_hit_rates_label(self) -> str:
        return f"{self.backtest_matches:,} past matches"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        """The defaults above are public (open-source repo): refuse to run production on them."""
        if not self.is_production:
            return self
        problems = []
        for name in ("jwt_secret", "ingest_hmac_secret", "proxy_shared_secret"):
            value = getattr(self, name).get_secret_value()
            if len(value) < 32 or value.startswith("change-me"):
                problems.append(f"{name.upper()} must be a random value of at least 32 characters")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if problems:
            raise ValueError("unsafe production settings: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
