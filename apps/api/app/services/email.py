"""Transactional email over SMTP (Mailpit locally). In the test environment messages go to OUTBOX."""
import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger, mask_email

log = get_logger(__name__)
OUTBOX: list[EmailMessage] = []


def _send_sync(msg: EmailMessage) -> None:
    s = get_settings()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)


async def send_email(to: str, subject: str, text: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    if s.environment == "test":
        OUTBOX.append(msg)
        return
    try:
        await asyncio.to_thread(_send_sync, msg)
        log.info("email_sent", to=mask_email(to), subject=subject)
    except OSError as e:
        log.error("email_failed", to=mask_email(to), error=str(e))


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
