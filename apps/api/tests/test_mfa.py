"""Two-factor sign-in (TOTP): enrolment, the two-step login, replay and brute-force limits, recovery codes,
refresh, Google, and the admin requirement."""
import pytest
from sqlalchemy import select

from app.core import totp
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import User
from app.services import access_tokens
from tests.helpers import (
    PASSWORD,
    csrf,
    enable_mfa,
    login,
    register_verified,
    reset_rate_limits,
    totp_code,
)

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of the RFC 6238 SHA1 key "12345678901234567890"


@pytest.mark.parametrize("t,expected", [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                        (1234567890, "89005924"), (2000000000, "69279037")])
def test_totp_matches_rfc6238_vectors(t, expected):
    assert totp.code_at(RFC_SECRET, t // 30, digits=8) == expected


def test_totp_window_and_single_use():
    now = 1_000_000_000.0
    step = totp.current_step(now)
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step), None, now) == step
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 1), None, now) == step - 1  # clock drift
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 2), None, now) is None       # too old
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step), step, now) is None           # replay
    assert totp.verify(RFC_SECRET, "000000x", None, now) is None


def test_secret_is_stored_encrypted():
    secret = totp.new_secret()
    stored = totp.encrypt_secret(secret)
    assert secret not in stored and totp.decrypt_secret(stored) == secret


async def _mfa_user(client) -> tuple[str, str, list[str]]:
    email = await register_verified(client)
    await login(client, email)
    secret, codes = await enable_mfa(client)
    await reset_rate_limits()
    return email, secret, codes


async def _password_step(client, email) -> dict:
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


async def test_login_needs_the_code_once_enabled(client):
    email, secret, _ = await _mfa_user(client)
    body = await _password_step(client, email)
    assert body == {"mfa_required": True}
    assert client.cookies.get("ap_access") is None and client.cookies.get("ap_mfa")
    assert (await client.get("/api/v1/me")).status_code == 401  # no session from the password alone

    r = await client.post("/api/v1/auth/mfa/verify", json={"code": "123456"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "mfa_invalid"
    r = await client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret, 1)})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["mfa_session"] is True
    me = (await client.get("/api/v1/me")).json()
    assert me["email"] == email and me["mfa_enabled"] and me["mfa_session"]


async def test_a_code_works_only_once(client):
    email, secret, _ = await _mfa_user(client)
    code = totp_code(secret, 1)
    await _password_step(client, email)
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": code})).status_code == 200
    await _password_step(client, email)
    r = await client.post("/api/v1/auth/mfa/verify", json={"code": code})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "mfa_invalid"


async def test_enable_consumed_code_cannot_be_replayed_at_login(client):
    email = await register_verified(client)
    await login(client, email)
    r = await client.post("/api/v1/me/mfa/setup", headers=csrf(client))
    secret = r.json()["secret"]
    code = totp_code(secret)
    r = await client.post("/api/v1/me/mfa/enable", json={"code": code, "current_password": PASSWORD},
                          headers=csrf(client))
    assert r.status_code == 200
    await _password_step(client, email)
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": code})).status_code == 401


async def test_verify_without_a_challenge_is_refused(client):
    r = await client.post("/api/v1/auth/mfa/verify", json={"code": "123456"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "mfa_expired"


async def test_challenge_ends_after_five_wrong_codes(client):
    email, secret, _ = await _mfa_user(client)
    await _password_step(client, email)
    for _ in range(5):
        await client.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
        await reset_rate_limits()
    r = await client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret, 1)})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "mfa_expired"


async def test_repeated_failures_lock_two_factor_for_the_account(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_max_failures", 2)
    email, secret, _ = await _mfa_user(client)
    await _password_step(client, email)
    for _ in range(2):
        await client.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
    r = await client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret, 1)})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "mfa_locked"


async def test_recovery_code_works_once(client):
    email, _, codes = await _mfa_user(client)
    assert len(codes) == 10
    await _password_step(client, email)
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": codes[0].lower()})).status_code == 200
    await _password_step(client, email)
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": codes[0]})).status_code == 401


async def test_enable_needs_current_password_and_a_valid_code(client):
    email = await register_verified(client)
    await login(client, email)
    secret = (await client.post("/api/v1/me/mfa/setup", headers=csrf(client))).json()["secret"]
    r = await client.post("/api/v1/me/mfa/enable", json={"code": totp_code(secret)}, headers=csrf(client))
    assert r.status_code == 400  # no password
    r = await client.post("/api/v1/me/mfa/enable", json={"code": "000000", "current_password": PASSWORD},
                          headers=csrf(client))
    assert r.status_code == 400
    assert (await client.get("/api/v1/me")).json()["mfa_enabled"] is False
    async with get_sessionmaker()() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        assert user.totp_secret_enc and secret not in user.totp_secret_enc  # encrypted at rest


async def test_disable_turns_the_second_step_off(client):
    email, secret, _ = await _mfa_user(client)
    r = await client.post("/api/v1/me/mfa/disable", json={"code": "000000"}, headers=csrf(client))
    assert r.status_code == 400
    r = await client.post("/api/v1/me/mfa/disable", json={"code": totp_code(secret, 1)}, headers=csrf(client))
    assert r.status_code == 200
    client.cookies.clear()
    body = await login(client, email)
    assert "user" in body and body["user"]["mfa_enabled"] is False


async def test_new_recovery_codes_replace_the_old_ones(client):
    email, secret, old = await _mfa_user(client)
    r = await client.post("/api/v1/me/mfa/recovery-codes", json={"code": totp_code(secret, 1)},
                          headers=csrf(client))
    assert r.status_code == 200
    new = r.json()["recovery_codes"]
    await _password_step(client, email)
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": old[1]})).status_code == 401
    assert (await client.post("/api/v1/auth/mfa/verify", json={"code": new[0]})).status_code == 200


async def test_refresh_keeps_the_two_factor_session(client):
    email, secret, _ = await _mfa_user(client)
    await _password_step(client, email)
    await client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret, 1)})
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["mfa_session"] is True


# ------------------------------------------------------------------------------------------ admins
async def _make_admin(email: str) -> None:
    async with get_sessionmaker()() as db:
        await access_tokens.set_role(db, email, "admin")
        await db.commit()
    await access_tokens.after_change()


async def test_admin_endpoints_need_two_factor(client):
    email = await register_verified(client)
    await _make_admin(email)
    await login(client, email)
    r = await client.get("/api/v1/admin/stats")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "mfa_required"
    await enable_mfa(client)
    assert (await client.get("/api/v1/admin/stats")).status_code == 200


async def test_admin_api_key_is_not_a_second_factor(client):
    email = await register_verified(client)
    await _make_admin(email)
    await login(client, email)
    await enable_mfa(client)
    key = (await client.post("/api/v1/me/api-key", headers=csrf(client))).json()["api_key"]
    client.cookies.clear()
    r = await client.get("/api/v1/admin/stats", headers={"x-api-key": key})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "mfa_reauth"


async def test_admin_mfa_can_be_switched_off_by_setting(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_mfa_required", False)
    email = await register_verified(client)
    await _make_admin(email)
    await login(client, email)
    assert (await client.get("/api/v1/admin/stats")).status_code == 200
