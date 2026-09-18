"""Production must not start on the public default secrets."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "x" * 40


def test_production_rejects_default_secrets():
    with pytest.raises(ValidationError, match="JWT_SECRET.*INGEST_HMAC_SECRET.*PROXY_SHARED_SECRET"):
        Settings(environment="production", jwt_secret="change-me-in-production-at-least-32-bytes!!",
                 ingest_hmac_secret="change-me-ingest-secret", proxy_shared_secret="", cookie_secure=True)


def test_production_rejects_insecure_cookies():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", jwt_secret=STRONG, ingest_hmac_secret=STRONG,
                 proxy_shared_secret=STRONG, cookie_secure=False)


def test_production_accepts_strong_secrets():
    s = Settings(environment="production", jwt_secret=STRONG, ingest_hmac_secret=STRONG,
                 proxy_shared_secret=STRONG, cookie_secure=True)
    assert s.is_production


def test_development_keeps_defaults():
    assert not Settings(environment="development").is_production
