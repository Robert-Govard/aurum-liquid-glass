"""Sends transactional email over plain SMTP (see core/config.py's
AURUM_SMTP_* settings) — stdlib smtplib only, no new dependency. Called
from routes/auth.py's register endpoint via FastAPI BackgroundTasks so a
slow or unreachable SMTP server never delays the HTTP response."""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_verification_email(to_email: str, token: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("AURUM_SMTP_HOST not set — skipping verification email to %s", to_email)
        return

    # rstrip: AURUM_PUBLIC_URL with a trailing slash (e.g. "https://host.com/")
    # would otherwise produce a double slash here, which LoginGate.tsx's
    # exact `location.pathname === "/verify-email"` check won't match —
    # silently breaking verification with no error message anywhere.
    verify_url = f"{settings.public_url.rstrip('/')}/verify-email?token={token}"
    message = EmailMessage()
    message["Subject"] = "Подтвердите email — Aurum"
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to_email
    message.set_content(
        "Здравствуйте!\n\n"
        "Чтобы подтвердить свой email в Aurum, перейдите по ссылке "
        f"(действительна 24 часа):\n{verify_url}\n\n"
        "Если вы не регистрировались в Aurum, просто проигнорируйте это письмо."
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError):
        # Runs inside a BackgroundTask after the HTTP response is already
        # sent — there's no request left to fail. Logging is the only
        # signal the operator gets that a verification email didn't go out.
        logger.exception("Failed to send verification email to %s", to_email)
