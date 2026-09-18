from tests.helpers import login, register_verified


async def test_follow_unfollow_is_idempotent_and_exported(client):
    data = await login(client, await register_verified(client))
    h = {"x-csrf-token": data["csrf_token"]}
    assert (await client.get("/api/v1/me/follows")).json() == {"matches": [], "leagues": []}
    for _ in range(2):  # following twice keeps one row
        r = await client.put("/api/v1/me/follows/match/t091901", headers=h)
        assert r.status_code == 200, r.text
    await client.put("/api/v1/me/follows/league/E0", headers=h)
    assert (await client.get("/api/v1/me/follows")).json() == {"matches": ["t091901"], "leagues": ["E0"]}
    export = (await client.get("/api/v1/me/export")).json()
    assert export["follows"] == {"matches": ["t091901"], "leagues": ["E0"]}
    r = await client.delete("/api/v1/me/follows/match/t091901", headers=h)
    assert r.json() == {"matches": [], "leagues": ["E0"]}


async def test_follow_input_is_validated_and_needs_sign_in(client):
    assert (await client.get("/api/v1/me/follows")).status_code == 401
    data = await login(client, await register_verified(client))
    h = {"x-csrf-token": data["csrf_token"]}
    assert (await client.put("/api/v1/me/follows/team/E0", headers=h)).status_code == 422
    assert (await client.put("/api/v1/me/follows/league/bad%20code", headers=h)).status_code == 422
    assert (await client.put("/api/v1/me/follows/league/E0")).status_code == 403  # CSRF header required
