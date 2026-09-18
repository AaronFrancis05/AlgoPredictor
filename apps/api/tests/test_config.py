"""Production must not start on the public default secrets or on unverified database TLS."""
import ssl

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings
from app.db.session import engine_kwargs, ssl_context

STRONG = "x" * 40
MFA_KEY = Fernet.generate_key().decode()
PG = "postgresql+asyncpg://u:p@db.example:5432/postgres"
SAFE = dict(environment="production", jwt_secret=STRONG, ingest_hmac_secret=STRONG, proxy_shared_secret=STRONG,
            cookie_secure=True, database_url=PG, db_ssl="verify-full", mfa_encryption_key=MFA_KEY)


def test_production_rejects_default_secrets():
    with pytest.raises(ValidationError, match="JWT_SECRET.*INGEST_HMAC_SECRET.*PROXY_SHARED_SECRET"):
        Settings(**{**SAFE, "jwt_secret": "change-me-in-production-at-least-32-bytes!!",
                    "ingest_hmac_secret": "change-me-ingest-secret", "proxy_shared_secret": ""})


def test_production_rejects_insecure_cookies():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(**{**SAFE, "cookie_secure": False})


@pytest.mark.parametrize("mode", ["require", "disable"])
def test_production_requires_verified_database_tls(mode):
    with pytest.raises(ValidationError, match="DB_SSL must be verify-full"):
        Settings(**{**SAFE, "db_ssl": mode})


@pytest.mark.parametrize("key,msg", [("", "MFA_ENCRYPTION_KEY must be set"), ("not-a-key", "not a valid Fernet key")])
def test_production_requires_mfa_key(key, msg):
    with pytest.raises(ValidationError, match=msg):
        Settings(**{**SAFE, "mfa_encryption_key": key})


def test_production_rejects_short_metrics_token():
    with pytest.raises(ValidationError, match="METRICS_TOKEN"):
        Settings(**{**SAFE, "metrics_token": "short"})


def test_production_accepts_strong_secrets():
    assert Settings(**SAFE).is_production


def test_development_keeps_defaults():
    assert not Settings(environment="development").is_production


def test_verify_full_checks_certificate_and_hostname_with_bundled_ca():
    ctx = ssl_context("verify-full", Settings().db_ssl_root_cert)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert any("Supabase Root 2021 CA" in str(c.get("subject")) for c in ctx.get_ca_certs())
    assert engine_kwargs(PG, "verify-full", False)["connect_args"]["ssl"].check_hostname


def test_verify_full_refuses_a_missing_ca_file():
    with pytest.raises(RuntimeError, match="does not exist"):
        ssl_context("verify-full", "certs/missing.crt")


def test_require_mode_does_not_verify():
    assert ssl_context("require").verify_mode == ssl.CERT_NONE
    assert ssl_context("disable") is None
