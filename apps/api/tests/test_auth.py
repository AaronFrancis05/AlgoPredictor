from tests.helpers import PASSWORD, login, register_verified


async def test_register_verify_login_me(client):
    email = await register_verified(client)
    data = await login(client, email)
    assert data["user"]["email"] == email and data["user"]["plan"] == "free"
    assert client.cookies.get("ap_access") and client.cookies.get("ap_csrf")
    r = await client.get("/api/v1/me")
    assert r.status_code == 200 and r.json()["email_verified"] is True


async def test_register_existing_email_is_not_revealed(client):
    email = await register_verified(client)
    r = await client.post("/api/v1/auth/register", json=dict(email=email, password=PASSWORD, confirm_age_18=True,
                                                             accept_terms=True))
    assert r.status_code == 201 and "If this address" in r.json()["message"]


async def test_register_requires_age_and_strong_password(client):
    r = await client.post("/api/v1/auth/register", json=dict(email="a@example.com", password="weakpassword",
                                                             confirm_age_18=False, accept_terms=True))
    assert r.status_code == 422
    fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert {"password", "confirm_age_18"} <= fields


async def test_lockout_after_repeated_failures(client):
    email = await register_verified(client)
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": "Wrong-pass-123"})
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 423


async def test_refresh_rotation_and_reuse_detection(client):
    email = await register_verified(client)
    await login(client, email)
    old_refresh = client.cookies.get("ap_refresh", path="/api/v1/auth")
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new_refresh = client.cookies.get("ap_refresh", path="/api/v1/auth")
    assert new_refresh and new_refresh != old_refresh
    # replaying the rotated token revokes the whole family
    client.cookies.set("ap_refresh", old_refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    client.cookies.set("ap_refresh", new_refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_failed_refresh_clears_the_session_cookies(client):
    email = await register_verified(client)
    await login(client, email)
    old_refresh = client.cookies.get("ap_refresh", path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    client.cookies.set("ap_refresh", old_refresh, path="/api/v1/auth")
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["detail"] == "Session revoked"
    cleared = {c.split("=", 1)[0] for c in r.headers.get_list("set-cookie") if "Max-Age=0" in c}
    assert {"ap_access", "ap_refresh", "ap_csrf"} <= cleared
    # no refresh cookie at all: still a 401 that clears whatever is left
    client.cookies.clear()
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and "ap_csrf" in r.headers.get("set-cookie", "")


async def test_csrf_required_for_cookie_authenticated_writes(client):
    email = await register_verified(client)
    data = await login(client, email)
    assert (await client.post("/api/v1/auth/logout")).status_code == 403
    r = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": data["csrf_token"]})
    assert r.status_code == 200


async def test_password_reset_flow_revokes_sessions(client):
    import re

    from app.services import email as mail
    email = await register_verified(client)
    await login(client, email)
    await client.post("/api/v1/auth/password/forgot", json={"email": email})
    token = re.search(r"token=([\w\-]+)", mail.OUTBOX[-1].get_content()).group(1)
    r = await client.post("/api/v1/auth/password/reset", json={"token": token, "password": "N3w-password!!"})
    assert r.status_code == 200
    assert (await client.post("/api/v1/auth/password/reset",
                              json={"token": token, "password": "N3w-password!!"})).status_code == 400
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "N3w-password!!"})
    assert r.status_code == 200


async def test_auth_rate_limit_returns_429(client):
    codes = []
    for _ in range(9):
        r = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
        codes.append(r.status_code)
    assert codes[:8] == [401] * 8 and codes[8] == 429


async def test_security_headers_present(client):
    r = await client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers.get("x-request-id")
