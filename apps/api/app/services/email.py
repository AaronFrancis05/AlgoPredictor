"""Transactional email: Resend's HTTPS API when RESEND_API_KEY is set, otherwise SMTP (Mailpit locally).
In the test environment messages go to OUTBOX. A failed send is logged and never fails the request: the user
can ask for another link (resend-verification / forgot-password)."""
import asyncio
import smtplib
import uuid
from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, mask_email

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


async def send_verification(to: str, token: str) -> None:
    url = f"{get_settings().public_web_url}/verify-email?token={token}"
    await send_email(to, "Confirm your AlgoPredict email",
                     f"Welcome to AlgoPredict.\n\nConfirm your email address:\n{url}\n\n"
                     "The link expires in 24 hours. If you did not sign up, ignore this message.")


async def send_password_reset(to: str, token: str) -> None:
    url = f"{get_settings().public_web_url}/reset-password?token={token}"
    await send_email(to, "Reset your AlgoPredict password",
                     f"A password reset was requested for this address.\n\nReset it here:\n{url}\n\n"
                     "The link expires in 24 hours. If you did not ask for this, ignore this message.")
