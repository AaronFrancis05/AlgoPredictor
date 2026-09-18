"""Resend delivery: request shape, links pointing at the web app, and failures that never break the request."""
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import email as mail


@pytest.fixture
def resend(monkeypatch):
    sent: list[httpx.Request] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if status["code"] >= 400:
            return httpx.Response(status["code"], json={"message": "The domain is not verified"})
        return httpx.Response(200, json={"id": "msg_123"})

    s = get_settings()
    monkeypatch.setattr(s, "resend_api_key", SecretStr("re_test_key"))
    monkeypatch.setattr(s, "smtp_from", "AlgoPredict <no-reply@example.com>")
    monkeypatch.setattr(s, "public_web_url", "https://web.example")
    monkeypatch.setattr(mail, "resend_transport", httpx.MockTransport(handler))
    return sent, status


async def test_verification_email_goes_to_resend(resend):
    sent, _ = resend
    await mail.send_verification("user@example.com", "tok123")
    assert len(sent) == 1
    req = sent[0]
    assert str(req.url) == mail.RESEND_URL
    assert req.headers["authorization"] == "Bearer re_test_key"
    assert req.headers["idempotency-key"]
    body = json.loads(req.content)
    assert body["from"] == "AlgoPredict <no-reply@example.com>"
    assert body["to"] == ["user@example.com"]
    assert "https://web.example/verify-email?token=tok123" in body["text"]


async def test_reset_email_links_to_reset_page(resend):
    sent, _ = resend
    await mail.send_password_reset("user@example.com", "tok456")
    assert "https://web.example/reset-password?token=tok456" in json.loads(sent[0].content)["text"]


async def test_resend_error_is_logged_not_raised(resend):
    sent, status = resend
    status["code"] = 403
    await mail.send_verification("user@example.com", "tok789")  # must not raise
    assert len(sent) == 1


async def test_register_still_succeeds_when_resend_fails(client, resend):
    _, status = resend
    status["code"] = 500
    r = await client.post("/api/v1/auth/register", json={
        "email": "resend-down@example.com", "password": "Sturdy-Password-2026!", "full_name": "T",
        "confirm_age_18": True, "accept_terms": True})
    assert r.status_code == 201
