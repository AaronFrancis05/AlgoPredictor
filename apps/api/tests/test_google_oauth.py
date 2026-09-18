import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.routers import auth as auth_router
from tests.helpers import PASSWORD, login, register_verified


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(auth_router.settings, "public_web_url", "https://web.example")
    claims = {"sub": "google-sub-1", "email": "Fan@Example.com", "email_verified": True, "name": "Fan"}

    async def exchange(code, verifier):
        return "id-token" if code == "good-code" else None

    def verify(token, nonce):
        return {**claims, "nonce": nonce}

    monkeypatch.setattr(auth_router, "_exchange_google_code", exchange)
    monkeypatch.setattr(auth_router, "_verify_google_id_token", verify)
    return claims


async def _start(client) -> dict:
    r = await client.get("/api/v1/auth/google/start")
    assert r.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}


async def test_google_start_not_configured(client, monkeypatch):
    monkeypatch.setattr(auth_router.settings, "google_client_id", "")
    monkeypatch.setattr(auth_router.settings, "public_web_url", "https://web.example")
    r = await client.get("/api/v1/auth/google/start")
    assert r.status_code == 302 and r.headers["location"] == "https://web.example/login?error=google_unavailable"


async def test_google_start_returns_to_web_origin_with_pkce(client, google):
    q = await _start(client)
    assert q["redirect_uri"] == "https://web.example/api/v1/auth/google/callback"
    assert q["client_id"] == "test-client-id" and q["code_challenge_method"] == "S256"
    assert q["state"] and q["nonce"]


async def test_google_callback_creates_user_and_session(client, google):
    q = await _start(client)
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": q["state"]})
    assert r.status_code == 302 and r.headers["location"] == "https://web.example/onboarding"
    assert client.cookies.get("ap_access") and client.cookies.get("ap_csrf")
    me = (await client.get("/api/v1/me")).json()
    assert me["email"] == "fan@example.com" and me["email_verified"] is True


async def test_google_callback_state_is_single_use(client, google):
    q = await _start(client)
    await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": q["state"]})
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": q["state"]})
    assert r.headers["location"] == "https://web.example/login?error=google"


async def test_google_callback_rejects_bad_code_and_unverified_email(client, google):
    q = await _start(client)
    r = await client.get("/api/v1/auth/google/callback", params={"code": "bad-code", "state": q["state"]})
    assert r.headers["location"] == "https://web.example/login?error=google"
    google["email_verified"] = False
    q = await _start(client)
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": q["state"]})
    assert r.headers["location"] == "https://web.example/login?error=google"


# ------------------------------------------------------- one account, two sign-in methods
async def _google_sign_in(client) -> str:
    q = await _start(client)
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": q["state"]})
    return r.headers["location"]


def _csrf(client) -> dict:
    return {"x-csrf-token": client.cookies.get("ap_csrf")}


async def test_google_sign_in_joins_existing_password_account(client, google):
    email = await register_verified(client)
    google.update(email=email, sub="sub-join")
    client.cookies.clear()
    assert await _google_sign_in(client) == "https://web.example/dashboard"  # age was confirmed at sign-up
    me = (await client.get("/api/v1/me")).json()
    assert me["email"] == email and me["has_password"] and me["google_linked"]
    client.cookies.clear()
    await login(client, email)  # the password still works


async def test_google_removes_password_nobody_verified(client, google):
    email = f"squat-{uuid.uuid4().hex[:6]}@example.com"
    r = await client.post("/api/v1/auth/register", json=dict(email=email, password=PASSWORD, confirm_age_18=True,
                                                             accept_terms=True))
    assert r.status_code == 201
    google.update(email=email, sub="sub-owner")
    await _google_sign_in(client)
    me = (await client.get("/api/v1/me")).json()
    assert me["email_verified"] and me["google_linked"] and not me["has_password"]
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 401


async def test_google_only_account_adds_then_changes_password(client, google):
    google.update(email=f"g-{uuid.uuid4().hex[:6]}@example.com", sub="sub-add-pw")
    await _google_sign_in(client)
    assert (await client.get("/api/v1/me")).json()["has_password"] is False
    r = await client.post("/api/v1/me/password", json={"password": PASSWORD}, headers=_csrf(client))
    assert r.status_code == 200, r.text
    new = "An0ther-password!"
    r = await client.post("/api/v1/me/password", json={"password": new}, headers=_csrf(client))
    assert r.status_code == 400  # changing needs the current password
    r = await client.post("/api/v1/me/password", json={"current_password": PASSWORD, "password": new},
                          headers=_csrf(client))
    assert r.status_code == 200
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": google["email"], "password": new})
    assert r.status_code == 200


async def test_link_google_with_a_different_address_then_unlink(client, google):
    email = await register_verified(client)
    await login(client, email)
    google.update(email="other-address@gmail.com", sub="sub-link")
    r = await client.post("/api/v1/me/google/link", headers=_csrf(client))
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": state})
    assert r.headers["location"] == "https://web.example/account?google=linked"
    client.cookies.clear()
    await _google_sign_in(client)  # that Google account now opens the password account
    assert (await client.get("/api/v1/me")).json()["email"] == email
    r = await client.delete("/api/v1/me/google", headers=_csrf(client))
    assert r.status_code == 200
    assert (await client.get("/api/v1/me")).json()["google_linked"] is False


async def test_link_refuses_google_account_owned_by_someone_else(client, google):
    google.update(email=f"first-{uuid.uuid4().hex[:6]}@example.com", sub="sub-taken")
    await _google_sign_in(client)
    client.cookies.clear()
    email = await register_verified(client)
    await login(client, email)
    r = await client.post("/api/v1/me/google/link", headers=_csrf(client))
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"code": "good-code", "state": state})
    assert r.headers["location"] == "https://web.example/account?google=in_use"


async def test_cannot_unlink_google_without_a_password(client, google):
    google.update(email=f"only-{uuid.uuid4().hex[:6]}@example.com", sub="sub-only")
    await _google_sign_in(client)
    r = await client.delete("/api/v1/me/google", headers=_csrf(client))
    assert r.status_code == 400
