"""Startup guards in app/main.py's lifespan.

Deliberately calls the check function directly with a monkeypatched setting
rather than driving the whole ASGI app's lifespan protocol: the test client
used across this suite (see conftest.py's `client` fixture) never sends
lifespan events in the first place (httpx's ASGITransport only forwards HTTP
requests), so exercising the real lifespan context manager here would need
machinery this codebase doesn't otherwise use. Testing the guard function in
isolation is both simpler and a faithful check of the actual behavior."""
import pytest

from app.core.config import get_settings
from app.main import _check_jwt_secret_is_configured


def test_check_jwt_secret_is_configured_raises_on_placeholder(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "change-me-in-production")
    with pytest.raises(RuntimeError, match="AURUM_JWT_SECRET"):
        _check_jwt_secret_is_configured()


def test_check_jwt_secret_is_configured_passes_with_real_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "a-real-randomly-generated-secret")
    _check_jwt_secret_is_configured()  # must not raise
