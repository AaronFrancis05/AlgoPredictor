"""Transactional email: Resend's HTTPS API when RESEND_API_KEY is set, otherwise SMTP (Mailpit locally).
In the test environment messages go to OUTBOX. A failed send is logged and never fails the request: the user
can ask for another link (resend-verification / forgot-password)."""
import asyncio
import hashlib
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, mask_email
from app.core.redis import get_redis

log = get_logger(__name__)
OUTBOX: list[EmailMessage] = []
RESEND_URL = "https://api.resend.com/emails"
resend_transport: httpx.AsyncBaseTransport | None = None  # replaced in tests


def _send_sync(msg: EmailMessage) -> None:
    s = get_settings()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)


async def _send_resend(api_key: str, sender: str, to: str, subject: str, text: str) -> str:
    """POST /emails; returns Resend's message id. The idempotency key stops a retried call sending twice."""
    async with httpx.AsyncClient(timeout=15, transport=resend_transport) as client:
        r = await client.post(RESEND_URL, json={"from": sender, "to": [to], "subject": subject, "text": text},
                              headers={"Authorization": f"Bearer {api_key}",
                                       "Idempotency-Key": uuid.uuid4().hex})
    if r.status_code >= 400:
        raise httpx.HTTPStatusError(f"Resend HTTP {r.status_code}: {r.text[:300]}", request=r.request, response=r)
    return r.json().get("id", "")


async def send_email(to: str, subject: str, text: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    if s.environment == "test" and resend_transport is None:
        OUTBOX.append(msg)
        return
    api_key = s.resend_api_key.get_secret_value()
    try:
        if api_key:
            message_id = await _send_resend(api_key, s.smtp_from, to, subject, text)
            log.info("email_sent", via="resend", id=message_id, to=mask_email(to), subject=subject)
        else:
            await asyncio.to_thread(_send_sync, msg)
            log.info("email_sent", via="smtp", to=mask_email(to), subject=subject)
    except (OSError, httpx.HTTPError) as e:
        log.error("email_failed", to=mask_email(to), subject=subject, error=str(e))


async def may_send(to: str, purpose: str) -> bool:
    """Guard for automatic emails, so nobody can spend the provider quota or flood one inbox with links:
    at most EMAIL_PER_RECIPIENT_PER_HOUR per address and purpose, and EMAIL_DAILY_BUDGET in total per UTC day.
    A refused send is logged and skipped; the endpoint's reply stays the same (it never says whether mail went out).
    Redis unavailable -> no send (cost first; the user can ask again)."""
    s = get_settings()
    who = hashlib.sha256(to.strip().lower().encode()).hexdigest()[:32]
    try:
        redis = get_redis()
        per_to = f"email:to:{purpose}:{who}"
        n = await redis.incr(per_to)
        if n == 1:
            await redis.expire(per_to, 3600)
        if n > s.email_per_recipient_per_hour:
            log.warning("email_skipped", reason="recipient_hourly_limit", to=mask_email(to), purpose=purpose)
            return False
        day = f"email:budget:{datetime.now(UTC):%Y%m%d}"
        used = await redis.incr(day)
        if used == 1:
            await redis.expire(day, 2 * 86400)
        if used > s.email_daily_budget:
            log.error("email_skipped", reason="daily_budget_exhausted", budget=s.email_daily_budget, purpose=purpose)
            return False
    except Exception as e:  # noqa: BLE001 - never fail the request over the guard
        log.error("email_guard_unavailable", error=str(e))
        return False
    return True


async def send_verification(to: str, token: str) -> None:
    if not await may_send(to, "verify"):
        return
    url = f"{get_settings().public_web_url}/verify-email?token={token}"
    await send_email(to, "Confirm your AlgoPredict email",
                     f"Welcome to AlgoPredict.\n\nConfirm your email address:\n{url}\n\n"
                     "The link expires in 24 hours. If you did not sign up, ignore this message.")


async def send_password_reset(to: str, token: str) -> None:
    if not await may_send(to, "reset"):
        return
    url =f"{get_settings().public_web_url}/reset-password?token={token}"
    await send_email(to, "Reset your AlgoPredict password",
                     f"A password reset was requested for this address.\n\nReset it here:\n{url}\n\n"
                     "The link expires in 24 hours. If you did not ask for this, ignore this message.")
