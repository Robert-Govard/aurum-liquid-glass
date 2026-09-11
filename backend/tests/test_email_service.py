"""services/email_service.py — stdlib smtplib only, no live SMTP server
in this test suite (see spec's testing constraints), so every test here
mocks smtplib.SMTP and asserts what it was called with."""
from unittest.mock import MagicMock, patch

from app.core.config import get_settings
from app.services.email_service import send_verification_email


def test_send_verification_email_noop_without_smtp_host(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    with patch("smtplib.SMTP") as mock_smtp:
        send_verification_email("user@example.com", "sometoken")
    mock_smtp.assert_not_called()


def test_send_verification_email_sends_via_smtp(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_from", "")
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "public_url", "https://example.com")

    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_conn
        send_verification_email("user@example.com", "sometoken")

    mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_conn.starttls.assert_called_once()
    mock_conn.login.assert_called_once_with("bot@example.com", "secret")
    mock_conn.send_message.assert_called_once()
    sent_message = mock_conn.send_message.call_args[0][0]
    assert sent_message["To"] == "user@example.com"
    assert "https://example.com/verify-email?token=sometoken" in sent_message.get_content()


def test_send_verification_email_skips_starttls_when_disabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 25)
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_use_tls", False)
    monkeypatch.setattr(settings, "public_url", "https://example.com")

    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = mock_conn
        send_verification_email("user@example.com", "sometoken")

    mock_conn.starttls.assert_not_called()
    mock_conn.login.assert_not_called()
    sent_message = mock_conn.send_message.call_args[0][0]
    assert sent_message["From"] == "noreply@example.com"
