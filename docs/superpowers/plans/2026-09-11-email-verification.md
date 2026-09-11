# Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make email ownership verification mandatory before a newly registered account can log in — registration sends a link by SMTP, the link logs the user in, and unverified accounts can't authenticate.

**Architecture:** Three new nullable columns on `User` (a token hash + expiry, no new table — only one verification token is ever outstanding per user). A new stdlib-`smtplib` email service, fired from `POST /auth/register` via FastAPI `BackgroundTasks` so an unreachable SMTP server never delays the HTTP response. `register()` stops returning a `TokenPair` (it's a `MessageResponse` now); `login()` gains a `403` check; a new `POST /auth/verify-email` spends the token and auto-logs in. The existing test suite's `client` fixture and `register_user()`/`_register()` helpers (52+ call sites) get fixed to keep working by flipping `is_email_verified` directly in the test database rather than driving a real email round-trip.

**Tech Stack:** FastAPI `BackgroundTasks`, stdlib `smtplib`/`email.message.EmailMessage` (no new dependency), SQLAlchemy/Alembic, existing JWT session infra (`core/security.py`).

**Spec:** `docs/superpowers/specs/2026-09-11-email-verification-design.md`

## Global Constraints

- Sending email is plain SMTP via env vars (`AURUM_SMTP_*`), stdlib `smtplib` only — no new dependency.
- Verification is **mandatory**: `POST /auth/login` returns `403` (not `401`) for a correct password on an unverified account, checked *after* the password check so an incorrect password never reveals verification state.
- Every pre-existing user gets `is_email_verified = TRUE` via the migration's backfill (`server_default=true`, then dropped) — only new registrations default to unverified.
- Verification link is valid for 24 hours.
- Re-registering an email that exists but is unverified: same password → resend (no second user created); different password, or already verified → the same `409` in both cases (no way to distinguish "doesn't exist" from "already verified" from the response).
- No separate "resend" endpoint — the frontend's resend button just calls `register()` again with the same email/password.
- Every new frontend string goes through `lib/i18n.ts` (`ru` and `en`, kept in sync).
- No browser and no real SMTP server available to the implementer — verify via `npm run build`/`pytest` and code review; actual email delivery and the link's landing page need manual verification once real SMTP credentials are in `.env`.

---

### Task 1: `User` model fields + migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/a1e4a2f9c318_add_email_verification_to_users.py`

**Interfaces:**
- Produces: `User.is_email_verified: bool`, `User.email_verification_token_hash: str | None`, `User.email_verification_expires_at: datetime | None` — consumed by Task 3's `auth_service.py`.

- [ ] **Step 1: Add the three columns to the model**

In `backend/app/models/user.py`, after the existing `last_login_at` field, add:

```python
    # Verification state for the email the account was registered with —
    # see services/auth_service.py's register()/login()/verify_email().
    # Only one verification token is ever outstanding per user (unlike
    # refresh_tokens, which intentionally keeps many rows per user for
    # multiple devices), so this is three columns here rather than a
    # separate table: a new registration/resend just overwrites the
    # previous token's hash and expiry.
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/a1e4a2f9c318_add_email_verification_to_users.py`:

```python
"""add email verification to users

Revision ID: a1e4a2f9c318
Revises: 5f8a1bc05518
Create Date: 2026-09-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1e4a2f9c318'
down_revision: Union[str, None] = '5f8a1bc05518'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every pre-existing account gets TRUE via the backfill default below —
    # only new registrations after this migration should ever start
    # unverified. Same two-step pattern as f2c8e4a917b3_add_risk_level_to_assets.py:
    # backfill existing rows with a server_default, then drop the default so
    # new inserts fall through to the model's own default=False.
    op.add_column('users', sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('users', 'is_email_verified', server_default=None)
    op.add_column('users', sa.Column('email_verification_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('email_verification_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'email_verification_expires_at')
    op.drop_column('users', 'email_verification_token_hash')
    op.drop_column('users', 'is_email_verified')
```

- [ ] **Step 3: Verify the migration applies cleanly**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (unmodified so far — `tests/conftest.py`'s session-scoped `_test_database` fixture runs `alembic upgrade head` against `aurum_test` before any test runs, so this step alone proves the migration doesn't error against the current schema chain).

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/a1e4a2f9c318_add_email_verification_to_users.py
git commit -m "Добавить поля подтверждения email в модель User"
```

**IMPORTANT — flag for the human partner, not something to act on in this task:** the backfill only gets exercised for real against the production `aurum` database, which the CI/test database never has rows in. Before deploying this migration to the real server, confirm with a manual `SELECT is_email_verified, count(*) FROM users GROUP BY 1;` after running it that every pre-existing row came back `TRUE`.

---

### Task 2: SMTP email service + config

**Files:**
- Create: `backend/app/services/email_service.py`
- Test: `backend/tests/test_email_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `send_verification_email(to_email: str, token: str) -> None` — consumed by Task 3's `auth_service.py` via `BackgroundTasks.add_task`.
- Produces: `Settings.smtp_host/smtp_port/smtp_user/smtp_password/smtp_from/smtp_use_tls/public_url` on `get_settings()`.

- [ ] **Step 1: Add SMTP settings to `Settings`**

In `backend/app/core/config.py`, inside the `Settings` class, after the existing `jwt_secret` field:

```python
    # Outbound SMTP for transactional email — currently only the
    # verification link sent by services/email_service.py. Empty host is
    # the same "feature just doesn't run" convention as coingecko_api_key
    # above: registration still works, the email is skipped (logged
    # instead of sent), nothing else breaks — but nobody can actually log
    # in afterward without it configured, since verification is mandatory.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    # Public base URL this instance is reachable at (e.g.
    # https://robertaurum.mooo.com:8443) — used to build the link inside
    # the verification email. Every self-hosted install has a different
    # one, so there's no sane default.
    public_url: str = ""
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_email_service.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_email_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.email_service'`

- [ ] **Step 4: Implement `email_service.py`**

Create `backend/app/services/email_service.py`:

```python
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

    verify_url = f"{settings.public_url}/verify-email?token={token}"
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_email_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Add the env vars to `.env.example`**

In `.env.example`, after the existing `# --- Auth ---` block:

```
# --- Email verification (optional but required for registration to be usable) ---
# Leave AURUM_SMTP_HOST empty and new accounts are created but never
# receive a verification link — since verification is mandatory to log
# in, nobody can actually finish registering until this is set up.
AURUM_SMTP_HOST=
AURUM_SMTP_PORT=587
AURUM_SMTP_USER=
AURUM_SMTP_PASSWORD=
AURUM_SMTP_FROM=
AURUM_SMTP_USE_TLS=true
# Public address this instance is reachable at — used to build the link
# inside the verification email (e.g. https://robertaurum.mooo.com:8443).
AURUM_PUBLIC_URL=
```

- [ ] **Step 7: Wire the env vars through `docker-compose.yml`**

In `docker-compose.yml`, in the `backend` service's `environment:` block, after `AURUM_JWT_SECRET`:

```yaml
      AURUM_SMTP_HOST: ${AURUM_SMTP_HOST:-}
      AURUM_SMTP_PORT: ${AURUM_SMTP_PORT:-587}
      AURUM_SMTP_USER: ${AURUM_SMTP_USER:-}
      AURUM_SMTP_PASSWORD: ${AURUM_SMTP_PASSWORD:-}
      AURUM_SMTP_FROM: ${AURUM_SMTP_FROM:-}
      AURUM_SMTP_USE_TLS: ${AURUM_SMTP_USE_TLS:-true}
      AURUM_PUBLIC_URL: ${AURUM_PUBLIC_URL:-}
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/email_service.py backend/tests/test_email_service.py backend/app/core/config.py .env.example docker-compose.yml
git commit -m "Добавить сервис отправки email для подтверждения регистрации"
```

---

### Task 3: Register/login/verify-email backend flow + test infrastructure

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/helpers.py`
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: `send_verification_email(to_email: str, token: str) -> None` from Task 2.
- Produces: `POST /auth/register` now returns `MessageResponse` (`{"message": str}`), status 201. `POST /auth/login` returns `403` for an unverified account. New `POST /auth/verify-email` (body `{"token": str}`) returns `TokenPair`.

This task changes behavior that the ENTIRE test suite's setup depends on — every one of the other 17 test files calls the `client` fixture, and 15 of them additionally call `tests/helpers.py`'s `register_user()`. Both must keep returning a real, already-authenticated session so nothing outside `test_auth.py`/`test_admin.py` has to change. The trick used throughout this task: register normally, then flip `is_email_verified = TRUE` directly in the test database (bypassing the real email), then log in for a real token pair — never touching the 52+ existing call sites' own code.

- [ ] **Step 1: Add the new schemas**

In `backend/app/schemas/auth.py`, after `RefreshRequest`:

```python
class VerifyEmailRequest(BaseModel):
    token: str


class MessageResponse(BaseModel):
    message: str
```

- [ ] **Step 2: Rewrite `auth_service.py`**

Replace the full contents of `backend/app/services/auth_service.py` with:

```python
"""Registration/login/token-refresh/logout/email-verification — the only
place that issues or revokes tokens; routes/auth.py stays a thin HTTP
wrapper around this."""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.seed import seed_default_app_settings, seed_default_categories
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import MessageResponse, RegisterRequest, TokenPair
from app.services.email_service import send_verification_email

EMAIL_VERIFICATION_TOKEN_TTL = timedelta(hours=24)


async def _issue_token_pair(session: AsyncSession, user_id: int) -> TokenPair:
    access = create_access_token(user_id)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(user_id)
    session.add(RefreshToken(user_id=user_id, token_hash=refresh_hash, expires_at=expires_at))
    await session.commit()
    return TokenPair(access_token=access, refresh_token=raw_refresh)


def _issue_verification_token(user: User) -> str:
    """Mutates `user` in place (caller commits) and returns the RAW token
    to email to the user — only its SHA-256 hash is ever persisted (see
    core/security.py's hash_token, the same scheme refresh tokens use).
    A new call always overwrites the previous token: only one verification
    token is ever outstanding per user."""
    raw_token = secrets.token_urlsafe(32)
    user.email_verification_token_hash = hash_token(raw_token)
    user.email_verification_expires_at = datetime.now(timezone.utc) + EMAIL_VERIFICATION_TOKEN_TTL
    return raw_token


async def register(
    session: AsyncSession, payload: RegisterRequest, background_tasks: BackgroundTasks
) -> MessageResponse:
    result = await session.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.is_email_verified or not verify_password(payload.password, existing.password_hash):
            # Same response whether the email is already verified or the
            # password just doesn't match this unverified account —
            # otherwise the response would let a caller tell verified
            # accounts apart from unverified ones by trying a password.
            raise HTTPException(status_code=409, detail="Email already registered")
        # Unverified account, correct password: resend instead of 409 —
        # this is also exactly what the frontend's "send again" button
        # calls (see spec: no separate resend endpoint).
        raw_token = _issue_verification_token(existing)
        await session.commit()
        background_tasks.add_task(send_verification_email, existing.email, raw_token)
        return MessageResponse(message="Verification email sent")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction

    await seed_default_categories(session, user.id)
    await seed_default_app_settings(session, user.id)

    raw_token = _issue_verification_token(user)
    await session.commit()
    background_tasks.add_task(send_verification_email, user.email, raw_token)
    return MessageResponse(message="Verification email sent")


async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_email_verified:
        # Checked AFTER the password check on purpose — a wrong password on
        # an unverified account must still look like a generic 401, not
        # hint that the account exists but isn't verified yet.
        raise HTTPException(status_code=403, detail="Email not verified")
    user.last_login_at = datetime.now(timezone.utc)
    return await _issue_token_pair(session, user.id)


async def verify_email(session: AsyncSession, raw_token: str) -> TokenPair:
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(User).where(
            User.email_verification_token_hash == token_hash,
            User.email_verification_expires_at >= now,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.is_email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    # The only place a brand-new user's last_login_at gets set for the
    # first time — register() no longer counts as a login since it no
    # longer issues a session; this does, immediately (see spec: "перешёл
    # по ссылке — и уже внутри приложения").
    user.last_login_at = now
    return await _issue_token_pair(session, user.id)


async def refresh(session: AsyncSession, raw_token: str) -> TokenPair:
    try:
        user_id = decode_refresh_token(raw_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    # Atomic conditional UPDATE, not select-then-mutate-then-commit-later:
    # the "is this token still valid" check and the revocation itself have
    # to happen as one database operation, or two concurrent presentations
    # of the same still-valid token (a race, or a client retry) could both
    # read revoked_at IS NULL before either commits and both walk away with
    # a live child pair — defeating rotation. Only one concurrent caller can
    # match revoked_at.is_(None) here; the other gets rowcount == 0. Same
    # pattern as logout() below.
    #
    # The `user_id.in_(active_user_ids)` clause folds in the "owning user is
    # still active" check without a separate SELECT: a disabled user's
    # refresh token must stop working immediately (see user_service's
    # update_user, which also revokes outstanding tokens the moment a user
    # is disabled — this is the lazy backstop for any token issued in the
    # narrow window around that), and doing it as a subquery inside the same
    # UPDATE keeps everything above atomic instead of reintroducing a
    # load-then-check race.
    active_user_ids = select(User.id).where(User.id == user_id, User.is_active.is_(True))
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at >= now,
            RefreshToken.user_id.in_(active_user_ids),
        )
        .values(revoked_at=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=401, detail="Refresh token is no longer valid")

    return await _issue_token_pair(session, user_id)


async def logout(session: AsyncSession, raw_token: str) -> None:
    token_hash = hash_token(raw_token)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await session.commit()
```

- [ ] **Step 3: Rewrite `routes/auth.py`**

Replace the full contents of `backend/app/api/routes/auth.py` with:

```python
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.services.auth_service import login, logout, refresh, register, verify_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse, status_code=201)
async def register_route(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    return await register(session, payload, background_tasks)


@router.post("/verify-email", response_model=TokenPair)
async def verify_email_route(payload: VerifyEmailRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await verify_email(session, payload.token)


@router.post("/login", response_model=TokenPair)
async def login_route(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await login(session, payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await refresh(session, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    await logout(session, payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
```

- [ ] **Step 4: Fix `tests/conftest.py`'s `client` fixture**

In `backend/tests/conftest.py`, change the import line:

```python
from sqlalchemy import text
```
to:
```python
from sqlalchemy import text, update
```

and add, near the other model imports at the top:
```python
from app.models.user import User
```

Then replace the `client` fixture with:

```python
@pytest_asyncio.fixture
async def client(test_sessionmaker) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        register_resp = await ac.post("/auth/register", json={"email": "test@example.com", "password": "hunter22"})
        assert register_resp.status_code == 201, register_resp.text

        # Registration alone no longer creates a session — a real account
        # needs its email verified first (see services/auth_service.py).
        # Flip it directly here rather than actually sending/reading an
        # email: this fixture just needs a working default user, not a
        # test of the verification flow itself (see test_auth.py for that).
        async with test_sessionmaker() as session:
            await session.execute(
                update(User).where(User.email == "test@example.com").values(is_email_verified=True)
            )
            await session.commit()

        login_resp = await ac.post("/auth/login", json={"email": "test@example.com", "password": "hunter22"})
        assert login_resp.status_code == 200, login_resp.text
        token = login_resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
    app.dependency_overrides.clear()
```

- [ ] **Step 5: Fix `tests/helpers.py`'s `register_user()`**

In `backend/tests/helpers.py`, replace the `register_user()` function with:

```python
async def register_user(client, email: str, password: str = "hunter22") -> dict:
    """Registers a second user for an isolation test (the `client` fixture
    already auto-registers and authenticates as one default user — use
    this to bring in another one and compare what each can/can't see).
    Returns a real TokenPair dict (access_token, refresh_token, token_type)
    for that user: registration alone no longer creates a session (see
    services/auth_service.py), so this bypasses actually sending/reading a
    verification email by flipping is_email_verified directly in the test
    database — an ad-hoc engine, not the `test_sessionmaker` fixture, so
    every one of this helper's call sites keeps working unchanged — then
    logs in for real, same trick as conftest.py's `client` fixture uses
    for its own default user."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.user import User
    from tests.conftest import TEST_DB_NAME, _url

    await client.post("/auth/register", json={"email": email, "password": password})

    engine = create_async_engine(_url(TEST_DB_NAME))
    try:
        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            await session.execute(update(User).where(User.email == email).values(is_email_verified=True))
            await session.commit()
    finally:
        await engine.dispose()

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()
```

- [ ] **Step 6: Fix `tests/test_admin.py`'s local `_register()` duplicate**

`test_admin.py` has its own private `_register()` helper that duplicates the same "register and hand back tokens" job — same fix, but simplest is to delete the duplicate and reuse the one just fixed in Step 5. In `backend/tests/test_admin.py`, add near the top imports:

```python
from tests.helpers import register_user as _register
```

and delete the existing local definition:

```python
async def _register(client, email: str) -> dict:
    resp = await client.post("/auth/register", json={"email": email, "password": "hunter22"})
    return resp.json()
```

All 16 existing `_register(...)` call sites in this file keep working unchanged.

- [ ] **Step 7: Run the full suite to confirm the infrastructure fix holds**

Run: `pytest -v`
Expected: every test file OTHER than `test_auth.py` passes unchanged (they don't test register/login behavior itself, just consume the `client` fixture and `register_user()`). `test_auth.py` will still show failures — that's Step 8.

- [ ] **Step 8: Rewrite the `test_auth.py` tests broken by the new register()/login() contract**

Add `from datetime import timedelta` to the existing `from datetime import datetime, timedelta, timezone` import (already present) — no change needed there, it's already imported. Add `update` to the existing `from sqlalchemy import select` line:

```python
from sqlalchemy import select, update
```

Replace `test_register_returns_token_pair`:

```python
async def test_register_returns_message_response(client):
    resp = await client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert resp.status_code == 201
    assert resp.json() == {"message": "Verification email sent"}
```

`test_register_rejects_duplicate_email` is unchanged — it registers, then re-registers the same email with a DIFFERENT password, which is still a `409` under the new rules (unverified account, wrong password). Leave it exactly as-is, and add two more cases next to it:

```python
async def test_register_rejects_duplicate_verified_email(client, test_sessionmaker):
    await client.post("/auth/register", json={"email": "verified@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(
            update(User).where(User.email == "verified@example.com").values(is_email_verified=True)
        )
        await session.commit()

    resp = await client.post("/auth/register", json={"email": "verified@example.com", "password": "hunter22"})
    assert resp.status_code == 409


async def test_register_resend_for_unverified_email_with_correct_password(client, test_sessionmaker):
    first = await client.post("/auth/register", json={"email": "resend@example.com", "password": "hunter22"})
    assert first.status_code == 201

    second = await client.post("/auth/register", json={"email": "resend@example.com", "password": "hunter22"})
    assert second.status_code == 201
    assert second.json() == {"message": "Verification email sent"}

    async with test_sessionmaker() as session:
        matches = (await session.execute(select(User).where(User.email == "resend@example.com"))).scalars().all()
        assert len(matches) == 1  # resend must not create a second account
```

Replace `test_login_with_correct_password`:

```python
async def test_login_with_correct_password(client, test_sessionmaker):
    await client.post("/auth/register", json={"email": "b@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "b@example.com").values(is_email_verified=True))
        await session.commit()

    resp = await client.post("/auth/login", json={"email": "b@example.com", "password": "hunter22"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_unverified_email_is_rejected(client):
    await client.post("/auth/register", json={"email": "unverified@example.com", "password": "hunter22"})
    resp = await client.post("/auth/login", json={"email": "unverified@example.com", "password": "hunter22"})
    assert resp.status_code == 403
```

`test_login_with_wrong_password` and `test_login_with_unknown_email` are unchanged — a wrong password or unknown email both fail before the verification check ever runs.

Replace `test_refresh_issues_new_pair_and_rotates`:

```python
async def test_refresh_issues_new_pair_and_rotates(client, test_sessionmaker):
    await client.post("/auth/register", json={"email": "d@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "d@example.com").values(is_email_verified=True))
        await session.commit()
    login_resp = await client.post("/auth/login", json={"email": "d@example.com", "password": "hunter22"})
    old_refresh = login_resp.json()["refresh_token"]

    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # the rotated-out token must no longer work
    reuse_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401

    # the new one does
    second_refresh_resp = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert second_refresh_resp.status_code == 200
```

`test_refresh_rejects_garbage_token` is unchanged.

Replace `test_concurrent_refresh_of_the_same_token_only_one_wins`:

```python
async def test_concurrent_refresh_of_the_same_token_only_one_wins(client, test_sessionmaker):
    """Regression test for the rotation race: two concurrent presentations
    of the same still-valid refresh token must not both succeed. The
    atomic conditional UPDATE in auth_service.refresh() (WHERE
    revoked_at IS NULL, checked and set in one statement) means Postgres
    serializes the two UPDATEs via row locking — the loser's WHERE clause
    finds the row already revoked and matches zero rows, so exactly one
    request gets a new token pair and the other is rejected."""
    await client.post("/auth/register", json={"email": "f@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "f@example.com").values(is_email_verified=True))
        await session.commit()
    login_resp = await client.post("/auth/login", json={"email": "f@example.com", "password": "hunter22"})
    old_refresh = login_resp.json()["refresh_token"]

    first_resp, second_resp = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": old_refresh}),
        client.post("/auth/refresh", json={"refresh_token": old_refresh}),
    )

    statuses = sorted([first_resp.status_code, second_resp.status_code])
    assert statuses == [200, 401], f"expected exactly one winner and one rejection, got {statuses}"
```

Replace `test_logout_revokes_the_refresh_token`:

```python
async def test_logout_revokes_the_refresh_token(client, test_sessionmaker):
    await client.post("/auth/register", json={"email": "e@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "e@example.com").values(is_email_verified=True))
        await session.commit()
    login_resp = await client.post("/auth/login", json={"email": "e@example.com", "password": "hunter22"})
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    reuse_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401
```

Replace `test_register_seeds_the_new_users_own_categories_and_settings` (it used to fetch `/auth/me` with the token `register()` returned — there is no token anymore, so it looks the user up by email instead, which tests the same seeding side effect):

```python
async def test_register_seeds_the_new_users_own_categories_and_settings(client, test_sessionmaker):
    resp = await client.post("/auth/register", json={"email": "seeded@example.com", "password": "hunter22"})
    assert resp.status_code == 201

    async with test_sessionmaker() as session:
        user_id = (await session.execute(select(User.id).where(User.email == "seeded@example.com"))).scalar_one()

        categories = (await session.execute(select(Category).where(Category.user_id == user_id))).scalars().all()
        assert len(categories) == 17  # 8 expense + 9 income, see DEFAULT_*_CATEGORIES in db/seed.py

        settings_row = (
            await session.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        ).scalar_one()
        assert settings_row.currency  # created, not left missing
```

`test_get_me_requires_auth` is unchanged.

Replace `test_login_and_register_set_last_login_at` — under the new design `register()` no longer sets `last_login_at` at all; the split is now between `verify_email()` (first-ever login, via the link) and `login()` (every login after that):

```python
async def test_register_does_not_set_last_login_at(client, test_sessionmaker):
    resp = await client.post("/auth/register", json={"email": "notyetloggedin@example.com", "password": "hunter22"})
    assert resp.status_code == 201

    async with test_sessionmaker() as session:
        user = (
            await session.execute(select(User).where(User.email == "notyetloggedin@example.com"))
        ).scalar_one()
        assert user.last_login_at is None  # registering alone is not a login anymore


async def test_verify_email_and_subsequent_login_set_last_login_at(client, test_sessionmaker, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "app.services.auth_service.send_verification_email",
        lambda to_email, token: captured.update(token=token),
    )

    await client.post("/auth/register", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert "token" in captured

    verify_resp = await client.post("/auth/verify-email", json={"token": captured["token"]})
    assert verify_resp.status_code == 200

    async with test_sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == "lastlogin@example.com"))).scalar_one()
        assert user.last_login_at is not None
        first_login = user.last_login_at

    login_resp = await client.post("/auth/login", json={"email": "lastlogin@example.com", "password": "hunter22"})
    assert login_resp.status_code == 200

    async with test_sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == "lastlogin@example.com"))).scalar_one()
        assert user.last_login_at is not None
        assert user.last_login_at >= first_login
```

Replace `test_get_me_returns_the_callers_own_email` (also updates its own stale comment about a since-changed `client` fixture history):

```python
async def test_get_me_returns_the_callers_own_email(client, test_sessionmaker):
    # Registers, verifies, and logs in explicitly rather than relying on
    # the `client` fixture's own default user — this test is specifically
    # about what /auth/me returns for an arbitrary caller's own token, not
    # about the fixture's default identity.
    await client.post("/auth/register", json={"email": "whoami@example.com", "password": "hunter22"})
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == "whoami@example.com").values(is_email_verified=True))
        await session.commit()
    login_resp = await client.post("/auth/login", json={"email": "whoami@example.com", "password": "hunter22"})
    token = login_resp.json()["access_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "email" in body
    assert "password" not in body and "password_hash" not in body
```

Finally, add the new verify-email-specific tests at the end of the file:

```python
async def test_verify_email_with_valid_token_returns_a_token_pair(client, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "app.services.auth_service.send_verification_email",
        lambda to_email, token: captured.update(token=token),
    )

    await client.post("/auth/register", json={"email": "verify@example.com", "password": "hunter22"})
    assert "token" in captured

    resp = await client.post("/auth/verify-email", json={"token": captured["token"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]


async def test_verify_email_marks_the_account_verified_and_clears_the_token(client, test_sessionmaker, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "app.services.auth_service.send_verification_email",
        lambda to_email, token: captured.update(token=token),
    )

    await client.post("/auth/register", json={"email": "verify2@example.com", "password": "hunter22"})
    await client.post("/auth/verify-email", json={"token": captured["token"]})

    async with test_sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == "verify2@example.com"))).scalar_one()
        assert user.is_email_verified is True
        assert user.email_verification_token_hash is None
        assert user.email_verification_expires_at is None


async def test_verify_email_with_unknown_token_fails(client):
    resp = await client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400


async def test_verify_email_with_expired_token_fails(client, test_sessionmaker, monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "app.services.auth_service.send_verification_email",
        lambda to_email, token: captured.update(token=token),
    )

    await client.post("/auth/register", json={"email": "expired@example.com", "password": "hunter22"})

    async with test_sessionmaker() as session:
        await session.execute(
            update(User)
            .where(User.email == "expired@example.com")
            .values(email_verification_expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await session.commit()

    resp = await client.post("/auth/verify-email", json={"token": captured["token"]})
    assert resp.status_code == 400
```

- [ ] **Step 9: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS, including every file outside `test_auth.py`/`test_admin.py` that only consumes the `client` fixture / `register_user()` / `_register()`.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/services/auth_service.py backend/app/api/routes/auth.py backend/tests/conftest.py backend/tests/helpers.py backend/tests/test_auth.py backend/tests/test_admin.py
git commit -m "Сделать подтверждение email обязательным для входа"
```

---

### Task 4: Frontend session logic (`lib/auth.ts`)

**Files:**
- Modify: `frontend/src/lib/auth.ts`

**Interfaces:**
- Consumes: nothing new — same `TokenPair`/`getApiBase()` this file already had.
- Produces: `AuthResult` gains `"verify_email_sent" | "email_not_verified"`; new `verifyEmail(token: string): Promise<AuthResult>` — consumed by Task 5's `VerifyEmailScreen.tsx`.

- [ ] **Step 1: Widen `AuthResult`**

In `frontend/src/lib/auth.ts`, change:

```ts
export type AuthResult = "ok" | "invalid" | "email_taken" | "error" | "unreachable";
```
to:
```ts
export type AuthResult = "ok" | "invalid" | "email_taken" | "error" | "unreachable" | "verify_email_sent" | "email_not_verified";
```

- [ ] **Step 2: Update `login()`**

Replace the body of `login()`:

```ts
export async function login(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch(`${getApiBase()}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (response.status === 401) return "invalid";
    if (response.status === 403) return "email_not_verified";
    if (!response.ok) return "error";
    const pair = (await response.json()) as TokenPair;
    storeTokenPair(pair);
    const user = await fetchCurrentUser(pair.access_token);
    setState({ user });
    return "ok";
  } catch {
    return "unreachable";
  }
}
```

- [ ] **Step 3: Update `register()`**

Replace the body of `register()` — it no longer receives or stores a `TokenPair`:

```ts
export async function register(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch(`${getApiBase()}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (response.status === 409) return "email_taken";
    if (!response.ok) return "error";
    return "verify_email_sent";
  } catch {
    return "unreachable";
  }
}
```

- [ ] **Step 4: Add `verifyEmail()`**

Add this new function directly after `register()`:

```ts
/** Spends a verification token from the link in the confirmation email —
 * on success this behaves exactly like login()/register() used to: it
 * stores the returned token pair and updates the session state, so
 * LoginGate reactively swaps from VerifyEmailScreen to the app itself. */
export async function verifyEmail(token: string): Promise<AuthResult> {
  try {
    const response = await fetch(`${getApiBase()}/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) return "error";
    const pair = (await response.json()) as TokenPair;
    storeTokenPair(pair);
    const user = await fetchCurrentUser(pair.access_token);
    setState({ user });
    return "ok";
  } catch {
    return "unreachable";
  }
}
```

- [ ] **Step 5: Verify the build still type-checks**

Run: `cd frontend && npm run build`
Expected: FAILS — `AuthScreen.tsx` still assumes `register()`'s old contract implicitly through `ERROR_KEYS`/rendering (it will still compile since nothing there references removed fields directly, but confirm by running it anyway; if it happens to pass here that's fine, Task 5 is what actually renders the new states).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/auth.ts
git commit -m "Обновить сессионную логику фронтенда под обязательное подтверждение email"
```

---

### Task 5: Frontend UI (resend button, verify screen, i18n)

**Files:**
- Modify: `frontend/src/components/auth/AuthScreen.tsx`
- Create: `frontend/src/components/auth/VerifyEmailScreen.tsx`
- Modify: `frontend/src/components/auth/LoginGate.tsx`
- Modify: `frontend/src/lib/i18n.ts`

**Interfaces:**
- Consumes: `verifyEmail(token)` and the widened `AuthResult` from Task 4.

- [ ] **Step 1: Add the new i18n keys**

In `frontend/src/lib/i18n.ts`, in the `ru` block, right after the existing `"auth.changeServer": "Сменить сервер",` line:

```ts
  "auth.errorEmailNotVerified": "Email не подтверждён. Проверьте почту или отправьте письмо ещё раз.",
  "auth.verifyEmailSent": "Мы отправили письмо для подтверждения на указанный email. Перейдите по ссылке из письма, чтобы войти.",
  "auth.resendVerification": "Отправить письмо ещё раз",
  "auth.verifying": "Подтверждаем email…",
  "auth.verifySuccess": "Email подтверждён, выполняем вход…",
  "auth.verifyError": "Ссылка недействительна или устарела. Попробуйте зарегистрироваться ещё раз, чтобы получить новое письмо.",
```

And in the `en` block, right after the existing `"auth.changeServer": "Change server",` line:

```ts
  "auth.errorEmailNotVerified": "Email not verified. Check your inbox or send the link again.",
  "auth.verifyEmailSent": "We've sent a verification link to that email. Follow it to sign in.",
  "auth.resendVerification": "Send the link again",
  "auth.verifying": "Verifying your email…",
  "auth.verifySuccess": "Email verified, signing you in…",
  "auth.verifyError": "This link is invalid or has expired. Try registering again to get a new one.",
```

- [ ] **Step 2: Wire the new states into `AuthScreen.tsx`**

In `frontend/src/components/auth/AuthScreen.tsx`, add an entry to `ERROR_KEYS`:

```ts
const ERROR_KEYS: Partial<Record<Status, string>> = {
  invalid: "auth.errorInvalidCredentials",
  email_taken: "auth.errorEmailTaken",
  error: "auth.errorGeneric",
  unreachable: "auth.errorUnreachable",
  email_not_verified: "auth.errorEmailNotVerified",
};
```

Replace this existing line inside the `<form>`:

```tsx
            {errorKey && <p className="text-sm text-danger">{t(errorKey as Parameters<typeof t>[0])}</p>}
```

with:

```tsx
            {status === "verify_email_sent" && (
              <p className="text-sm text-text-secondary">{t("auth.verifyEmailSent")}</p>
            )}
            {errorKey && <p className="text-sm text-danger">{t(errorKey as Parameters<typeof t>[0])}</p>}
```

Then, right after the existing "switch mode" `<button>` (the one that toggles `mode` between login/register) and before the `isNative()` block, add the resend button:

```tsx
          {status === "email_not_verified" && (
            <button
              type="button"
              onClick={async () => {
                setStatus("submitting");
                setStatus(await register(email, password));
              }}
              className="text-xs text-text-secondary underline-offset-2 hover:underline"
            >
              {t("auth.resendVerification")}
            </button>
          )}
```

`register` is already imported in this file (used in `handleSubmit`), so no new import is needed.

- [ ] **Step 3: Create `VerifyEmailScreen.tsx`**

Create `frontend/src/components/auth/VerifyEmailScreen.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { Card, CardContent } from "@/components/ui/Card";
import { verifyEmail } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Status = "verifying" | "success" | "error";

/** Rendered by LoginGate instead of AuthScreen when there's no session and
 * the current path is /verify-email — the destination of the link sent by
 * the backend's email_service.py. Reads the token from the query string
 * and spends it via lib/auth.ts's verifyEmail(); on success that function
 * updates the shared session state itself, so LoginGate reactively swaps
 * to rendering the app the moment this resolves — this screen only ever
 * needs to show progress or failure, never navigate anywhere on success. */
export function VerifyEmailScreen() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<Status>("verifying");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      return;
    }
    let cancelled = false;
    void verifyEmail(token).then((result) => {
      if (!cancelled) setStatus(result === "ok" ? "success" : "error");
    });
    return () => {
      cancelled = true;
    };
    // Deliberately runs once on mount only — the token in the URL never changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-4 p-6 pt-8 text-center sm:p-8">
          <Logo size={40} />
          <p className="text-sm text-text-secondary">
            {status === "verifying" && t("auth.verifying")}
            {status === "success" && t("auth.verifySuccess")}
            {status === "error" && t("auth.verifyError")}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Wire it into `LoginGate.tsx`**

In `frontend/src/components/auth/LoginGate.tsx`, add the import:

```tsx
import { useLocation } from "react-router-dom";
import { VerifyEmailScreen } from "@/components/auth/VerifyEmailScreen";
```

Add `const location = useLocation();` inside the component, alongside the existing `useAuthState()`/`useState()` calls, then replace:

```tsx
  if (!accessToken) {
    return <AuthScreen />;
  }
```

with:

```tsx
  if (!accessToken) {
    return location.pathname === "/verify-email" ? <VerifyEmailScreen /> : <AuthScreen />;
  }
```

- [ ] **Step 5: Verify the build**

Run: `cd frontend && npm run build`
Expected: PASS (`tsc -b` then `vite build`, no type errors).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/auth/AuthScreen.tsx frontend/src/components/auth/VerifyEmailScreen.tsx frontend/src/components/auth/LoginGate.tsx frontend/src/lib/i18n.ts
git commit -m "Добавить экран подтверждения email и повторную отправку письма"
```

---

## Manual verification (not automatable by the implementer)

After this plan merges and real `AURUM_SMTP_*`/`AURUM_PUBLIC_URL` values are set in `.env`:
1. Register a new account, confirm the email actually arrives and its link points at `AURUM_PUBLIC_URL/verify-email?token=...`.
2. Click the link, confirm it logs straight into the app.
3. Try logging into an unverified account, confirm the "email not verified" message and resend button appear and the resend actually delivers a second email.
4. Confirm every pre-existing real account (in the production `aurum` database, not `aurum_test`) still logs in without any verification prompt after the migration runs.
