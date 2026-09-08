# Multi-Tenant Auth Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user registration, login, JWT-based authentication, and a
basic admin capability to Aurum's backend, without touching any existing
router, service, model, or test.

**Architecture:** Two new tables (`users`, `refresh_tokens`), a
`app/core/security.py` module for password hashing and JWT issuing/
verification, an `auth_service` (register/login/refresh/logout) behind
`/api/auth/*`, `get_current_user`/`get_current_admin` FastAPI dependencies,
and a `user_service` behind `/api/admin/*`. Every existing domain table
(accounts, transactions, categories, ...) is untouched by this plan — they
get a `user_id` column and per-request scoping in a follow-up plan
("multi-tenant data isolation") once this foundation exists. Until that
follow-up plan lands, the app remains usable exactly as it is today
(single shared dataset) — this plan only adds new, independent
functionality alongside it.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2,
`bcrypt` (password hashing — used directly rather than through `passlib`,
whose bcrypt backend emits spurious version warnings against bcrypt>=4),
`PyJWT` (token issuing/verification).

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- No email verification and no password-reset flow — do not build either.
- Registration is open to anyone (no invite codes).
- Access tokens: JWT, HS256, 15-minute expiry, stateless (never checked
  against the database).
- Refresh tokens: JWT, HS256, 30-day expiry, additionally tracked in the
  `refresh_tokens` table by hash (never the raw token) so they're
  individually revocable; a refresh **rotates** the token — the used one is
  marked `revoked_at` and a new one is issued.
- Passwords are hashed with `bcrypt`; a plaintext password must never be
  logged, stored, or returned in a response.
- No Postgres Row-Level Security — isolation (in the follow-up plan) is
  application-level only.
- This plan does not modify `app/api/routes/{accounts,transactions,...}.py`
  or any file under `app/services/` except by adding new ones. It also does
  not touch `AURUM_BASIC_AUTH_USER`/`AURUM_BASIC_AUTH_PASSWORD` or nginx's
  `auth_basic` — that retirement happens in the follow-up plan, once
  existing routers actually enforce per-user auth and Basic Auth becomes
  redundant.

---

## Task 1: Add auth dependencies

**Files:**
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: the `bcrypt`, `jwt` (PyJWT), and `pydantic.EmailStr` (needs the
  `email-validator` extra) imports every later task in this plan relies on.

- [ ] **Step 1: Add the three new pins**

Modify `backend/requirements.txt` — append after the existing `httpx` line:

```
bcrypt==4.2.1
pyjwt==2.10.1
email-validator==2.2.0
```

- [ ] **Step 2: Install and verify**

Run: `docker compose exec backend pip install -r requirements.txt`

Then: `docker compose exec backend python -c "import bcrypt, jwt; from pydantic import EmailStr; print('ok')"`

Expected: prints `ok` with no `ImportError`.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "Добавить зависимости для аутентификации (bcrypt, PyJWT, email-validator)"
```

---

## Task 2: `User` and `RefreshToken` models + migration

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/refresh_token.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/5c9e2a7f1b34_add_users_and_refresh_tokens.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `User` (`id`, `email`, `password_hash`, `is_admin`, `is_active`,
  `created_at`) and `RefreshToken` (`id`, `user_id`, `token_hash`,
  `expires_at`, `revoked_at`), importable as `from app.models.user import
  User` / `from app.models.refresh_token import RefreshToken`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth.py`:

```python
"""Auth: registration, login, token refresh/rotation, logout."""
from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.models.user import User


async def test_user_and_refresh_token_tables_exist(test_sessionmaker):
    async with test_sessionmaker() as session:
        session.add(User(email="probe@example.com", password_hash="x"))
        await session.flush()
        user_id = (await session.execute(select(User.id).where(User.email == "probe@example.com"))).scalar_one()
        session.add(RefreshToken(user_id=user_id, token_hash="y" * 64, expires_at="2030-01-01"))
        await session.commit()

        stored = (await session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))).scalar_one()
        assert stored.revoked_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.user'`

- [ ] **Step 3: Create the `User` model**

Create `backend/app/models/user.py`:

```python
"""A registered account. Every domain table (accounts, transactions, ...)
gets its own user_id FK pointing here (added in the follow-up "multi-tenant
data isolation" plan) — deleting a User cascades to all of it."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Flipped off by an admin (see routes/admin.py) to disable a login
    # without deleting the account or its data.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Create the `RefreshToken` model**

Create `backend/app/models/refresh_token.py`:

```python
"""One issued refresh token, tracked so it can be revoked (logout, or
rotated out when used to mint a new pair — see services/auth_service.py)
without waiting for its own expiry. Only a SHA-256 hash of the token is
stored (see core/security.py:hash_token), never the raw value, so a leaked
database dump doesn't hand over live sessions."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Register both models**

Modify `backend/app/models/__init__.py` — add imports and `__all__` entries:

```python
from app.models.account import Account
from app.models.asset import Asset, AssetValuation
from app.models.budget import Budget
from app.models.category import Category
from app.models.crypto import CryptoHolding, CryptoPortfolio, CryptoSyncState, CryptoTransaction
from app.models.goal import Goal, GoalContribution
from app.models.recurring import RecurringTransaction
from app.models.refresh_token import RefreshToken
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionSplit
from app.models.user import User

__all__ = [
    "Account",
    "AppSettings",
    "Asset",
    "AssetValuation",
    "Budget",
    "Category",
    "CryptoHolding",
    "CryptoPortfolio",
    "CryptoSyncState",
    "CryptoTransaction",
    "Goal",
    "GoalContribution",
    "RecurringTransaction",
    "RefreshToken",
    "Tag",
    "Transaction",
    "TransactionSplit",
    "User",
]
```

- [ ] **Step 6: Register both models with Alembic**

Modify `backend/alembic/env.py` — the `from app.models import (...)` block
gains `RefreshToken` and `User`:

```python
from app.models import (  # noqa: F401 — registers metadata
    Account,
    AppSettings,
    Asset,
    AssetValuation,
    Budget,
    Category,
    CryptoHolding,
    CryptoSyncState,
    CryptoTransaction,
    Goal,
    GoalContribution,
    RecurringTransaction,
    RefreshToken,
    Tag,
    Transaction,
    TransactionSplit,
    User,
)
```

- [ ] **Step 7: Write the migration**

The current head revision is `c4e8f61a9d23` (`add_crypto_30d_1y_change`).
Create `backend/alembic/versions/5c9e2a7f1b34_add_users_and_refresh_tokens.py`:

```python
"""add users and refresh_tokens

Revision ID: 5c9e2a7f1b34
Revises: c4e8f61a9d23
Create Date: 2026-09-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c9e2a7f1b34'
down_revision: Union[str, None] = 'c4e8f61a9d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])


def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_table('users')
```

- [ ] **Step 8: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/test_auth.py -v`
Expected: PASS (the `_test_database` fixture runs `alembic upgrade head`
against `aurum_test` before any test executes, so the new tables exist).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user.py backend/app/models/refresh_token.py \
  backend/app/models/__init__.py backend/alembic/env.py \
  backend/alembic/versions/5c9e2a7f1b34_add_users_and_refresh_tokens.py \
  backend/tests/test_auth.py
git commit -m "Добавить модели User и RefreshToken + миграцию"
```

---

## Task 3: Password hashing + JWT utilities

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: nothing beyond `get_settings()` from `app.core.config` (Task 4
  adds the `jwt_secret` field this reads — write this task's tests with
  `monkeypatch` setting it directly so this task doesn't depend on Task 4's
  ordering).
- Produces: `hash_password(password: str) -> str`,
  `verify_password(password: str, password_hash: str) -> bool`,
  `create_access_token(user_id: int) -> str`,
  `decode_access_token(token: str) -> int` (raises `jwt.PyJWTError`),
  `create_refresh_token(user_id: int) -> tuple[str, str, datetime]` (raw
  token, sha256 hash, expiry), `decode_refresh_token(token: str) -> int`
  (raises `jwt.PyJWTError`), `hash_token(token: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_auth.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.core import security


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "test-secret-do-not-use-in-prod")


def test_password_hash_roundtrip():
    hashed = security.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    token = security.create_access_token(user_id=42)
    assert security.decode_access_token(token) == 42


def test_access_token_rejects_tampering():
    token = security.create_access_token(user_id=42)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(token + "x")


def test_access_token_rejects_expired():
    now = datetime.now(timezone.utc)
    payload = {"sub": "42", "type": "access", "iat": now, "exp": now - timedelta(seconds=1)}
    expired = pyjwt.encode(payload, get_settings().jwt_secret, algorithm=security.JWT_ALGORITHM)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token(expired)


def test_refresh_token_roundtrip_and_hash():
    raw, token_hash, expires_at = security.create_refresh_token(user_id=7)
    assert security.decode_refresh_token(raw) == 7
    assert security.hash_token(raw) == token_hash
    assert expires_at > datetime.now(timezone.utc)


def test_access_token_rejected_by_decode_refresh_token():
    access = security.create_access_token(user_id=1)
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_refresh_token(access)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_auth.py -v -k "password_hash or access_token or refresh_token"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.security'`

- [ ] **Step 3: Implement `app/core/security.py`**

Create `backend/app/core/security.py`:

```python
"""Password hashing and JWT access/refresh token helpers.

bcrypt is used directly rather than through passlib — passlib's bcrypt
backend has been stuck on old pins and emits spurious "error reading
bcrypt version" warnings against bcrypt>=4, so this sidesteps that
entirely with one well-maintained dependency.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Returns the user id encoded in a valid, unexpired access token.
    Raises jwt.PyJWTError (caught by callers, e.g. api/deps.py) if the
    token is invalid, expired, or not actually an access token."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return int(payload["sub"])


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (raw_jwt, sha256_hash_of_jwt, expires_at). Callers persist
    only the hash (see models/refresh_token.py) and hash whatever token a
    client presents later to compare against it — the raw JWT itself is
    never stored."""
    now = datetime.now(timezone.utc)
    expires_at = now + REFRESH_TOKEN_TTL
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, get_settings().jwt_secret, algorithm=JWT_ALGORITHM)
    return token, hash_token(token), expires_at


def decode_refresh_token(token: str) -> int:
    """Raises jwt.PyJWTError if invalid, expired, or not a refresh token.
    Does NOT check revocation — callers must additionally look up
    hash_token(token) in the refresh_tokens table (see
    services/auth_service.py:refresh)."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    return int(payload["sub"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_auth.py -v`
Expected: PASS (all tests in the file, including Task 2's).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_auth.py
git commit -m "Добавить хеширование паролей и JWT-утилиты"
```

---

## Task 4: Config + `.env.example`

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `Settings.jwt_secret: str`, read by `app/core/security.py`
  (Task 3) via `get_settings().jwt_secret`.

- [ ] **Step 1: Add the setting**

Modify `backend/app/core/config.py` — add a field to the `Settings` class,
right after `coingecko_api_key`:

```python
    # CoinGecko Demo API key (free, no card required — https://www.coingecko.com/en/api/pricing)
    # for services/crypto_service.py's price lookups. Empty by default; the
    # Crypto tab's endpoints 400 with a clear message until this is set,
    # rather than silently hitting CoinGecko's much stingier keyless tier.
    coingecko_api_key: str = ""

    # Signing key for access/refresh JWTs (see core/security.py). The
    # placeholder default only works because every token it would ever sign
    # is worthless without a real deployment behind it — set a real random
    # value (e.g. `openssl rand -hex 32`) before exposing this instance to
    # anyone.
    jwt_secret: str = "change-me-in-production"
```

- [ ] **Step 2: Document it in `.env.example`**

Modify `.env.example` — add a new section after `--- Crypto tab ... ---`
and before `--- Basic auth ... ---`:

```
# --- Auth ---
# Signing key for login sessions. Generate a real one with:
#   openssl rand -hex 32
# Leaving the placeholder means anyone who can read this file could forge
# a valid session for any account.
AURUM_JWT_SECRET=change-me-in-production
```

- [ ] **Step 3: Verify the app still boots**

Run: `docker compose up -d --build backend` then `docker compose logs backend --tail 20`
Expected: no startup errors; `Settings()` still constructs (pydantic-settings
picks up the new field with its default when `AURUM_JWT_SECRET` isn't set).

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py .env.example
git commit -m "Добавить настройку AURUM_JWT_SECRET"
```

---

## Task 5: Auth request/response schemas

**Files:**
- Create: `backend/app/schemas/auth.py`

**Interfaces:**
- Produces: `RegisterRequest(email, password)`, `LoginRequest(email,
  password)`, `RefreshRequest(refresh_token)`, `TokenPair(access_token,
  refresh_token, token_type="bearer")` — all Pydantic `BaseModel`s.

- [ ] **Step 1: Create the schemas**

Create `backend/app/schemas/auth.py`:

```python
"""Request/response shapes for /api/auth/*."""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `docker compose exec backend python -c "from app.schemas.auth import RegisterRequest, LoginRequest, RefreshRequest, TokenPair; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/auth.py
git commit -m "Добавить Pydantic-схемы для /api/auth"
```

---

## Task 6: Auth service (register/login/refresh/logout)

**Files:**
- Create: `backend/app/services/auth_service.py`
- Test: `backend/tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: `User`, `RefreshToken` (Task 2); `hash_password`,
  `verify_password`, `create_access_token`, `create_refresh_token`,
  `decode_refresh_token`, `hash_token` (Task 3); `RegisterRequest`,
  `TokenPair` (Task 5).
- Produces: `register(session, payload: RegisterRequest) -> TokenPair`,
  `login(session, email: str, password: str) -> TokenPair`,
  `refresh(session, raw_token: str) -> TokenPair`,
  `logout(session, raw_token: str) -> None` — all raise
  `fastapi.HTTPException` on failure (409 on duplicate email, 401 on bad
  credentials / invalid or revoked refresh token).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_auth.py` (uses the existing `client` fixture
from `conftest.py`, which already points at a clean, migrated test
database):

```python
async def test_register_returns_token_pair(client):
    resp = await client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


async def test_register_rejects_duplicate_email(client):
    await client.post("/auth/register", json={"email": "dup@example.com", "password": "hunter22"})
    resp = await client.post("/auth/register", json={"email": "dup@example.com", "password": "different1"})
    assert resp.status_code == 409


async def test_login_with_correct_password(client):
    await client.post("/auth/register", json={"email": "b@example.com", "password": "hunter22"})
    resp = await client.post("/auth/login", json={"email": "b@example.com", "password": "hunter22"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_wrong_password(client):
    await client.post("/auth/register", json={"email": "c@example.com", "password": "hunter22"})
    resp = await client.post("/auth/login", json={"email": "c@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


async def test_login_with_unknown_email(client):
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever1"})
    assert resp.status_code == 401


async def test_refresh_issues_new_pair_and_rotates(client):
    register_resp = await client.post("/auth/register", json={"email": "d@example.com", "password": "hunter22"})
    old_refresh = register_resp.json()["refresh_token"]

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


async def test_refresh_rejects_garbage_token(client):
    resp = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_logout_revokes_the_refresh_token(client):
    register_resp = await client.post("/auth/register", json={"email": "e@example.com", "password": "hunter22"})
    refresh_token = register_resp.json()["refresh_token"]

    logout_resp = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    reuse_resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_auth.py -v -k "register or login or refresh or logout"`
Expected: FAIL — 404s, since `/auth/*` routes don't exist yet (this task
builds the service; Task 7 wires the routes — these tests won't fully pass
until Task 7 is also done, which is fine: keep them red until then, per
Step 4 below).

- [ ] **Step 3: Implement `app/services/auth_service.py`**

Create `backend/app/services/auth_service.py`:

```python
"""Registration/login/token-refresh/logout — the only place that issues or
revokes tokens; routes/auth.py stays a thin HTTP wrapper around this."""
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException
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
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenPair


async def _issue_token_pair(session: AsyncSession, user_id: int) -> TokenPair:
    access = create_access_token(user_id)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(user_id)
    session.add(RefreshToken(user_id=user_id, token_hash=refresh_hash, expires_at=expires_at))
    await session.commit()
    return TokenPair(access_token=access, refresh_token=raw_refresh)


async def register(session: AsyncSession, payload: RegisterRequest) -> TokenPair:
    existing = await session.execute(select(User.id).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # assigns user.id without ending the transaction
    return await _issue_token_pair(session, user.id)


async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return await _issue_token_pair(session, user.id)


async def refresh(session: AsyncSession, raw_token: str) -> TokenPair:
    try:
        user_id = decode_refresh_token(raw_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    token_hash = hash_token(raw_token)
    result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now or stored.user_id != user_id:
        raise HTTPException(status_code=401, detail="Refresh token is no longer valid")

    stored.revoked_at = now
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

- [ ] **Step 4: Leave tests red until Task 7**

These tests hit HTTP routes (`/auth/register`, etc.) that don't exist
until Task 7 wires `auth_service` into the router layer. Don't chase this
further in this task — proceed to Task 7, then come back and run the full
file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_auth.py
git commit -m "Добавить auth_service: регистрация, вход, обновление и отзыв токенов"
```

---

## Task 7: Auth routes

**Files:**
- Create: `backend/app/api/routes/auth.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `register`, `login`, `refresh`, `logout` (Task 6);
  `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `TokenPair` (Task 5);
  `get_session` (existing, `app/api/deps.py`).
- Produces: `POST /api/auth/register` (201), `POST /api/auth/login` (200),
  `POST /api/auth/refresh` (200), `POST /api/auth/logout` (204).

- [ ] **Step 1: Create the router**

Create `backend/app/api/routes/auth.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.services.auth_service import login, logout, refresh, register

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register_route(payload: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await register(session, payload)


@router.post("/login", response_model=TokenPair)
async def login_route(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await login(session, payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    return await refresh(session, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout_route(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> None:
    await logout(session, payload.refresh_token)
```

- [ ] **Step 2: Wire it into the app**

Modify `backend/app/main.py` — add `auth` to the routes import (alphabetical,
before `backup`):

```python
from app.api.routes import (
    accounts,
    advice,
    assets,
    auth,
    backup,
    budgets,
    cash_flow,
    categories,
    crypto,
    dashboard,
    goals,
    insights,
    net_worth,
    recurring,
    reports,
    settings as settings_routes,
    tags,
    transactions,
)
```

And add the router alongside the others (right after the `app = FastAPI(...)`
block and the CORS middleware, before `app.include_router(dashboard.router, ...)`):

```python
app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
```

- [ ] **Step 3: Run the full auth test file**

Run: `docker compose exec backend pytest tests/test_auth.py -v`
Expected: PASS — every test from Tasks 2, 3, and 6.

- [ ] **Step 4: Run the whole existing suite to confirm no regression**

Run: `docker compose exec backend pytest -v`
Expected: PASS — every pre-existing test file is untouched by this plan and
must still be green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/main.py
git commit -m "Подключить роуты /api/auth/*"
```

---

## Task 8: `get_current_user` / `get_current_admin` dependencies

**Files:**
- Modify: `backend/app/api/deps.py`
- Test: `backend/tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: `decode_access_token` (Task 3), `User` (Task 2), `get_session`
  (existing).
- Produces: `get_current_user(...) -> User` and
  `get_current_admin(current_user: User = Depends(get_current_user)) ->
  User` — both usable as FastAPI `Depends(...)` in any route. Later tasks
  (the follow-up "multi-tenant data isolation" plan) import
  `get_current_user` from here to protect existing routers; this plan uses
  `get_current_admin` immediately in Task 9.

- [ ] **Step 1: Write the failing test**

This dependency is most naturally tested through a real protected route —
Task 9's admin routes are the first ones to use it, so its test coverage
lives in `test_admin.py` (Task 9) rather than being duplicated here. This
step is a placeholder-free no-op: skip straight to implementation, since
there is no standalone unit to red-test in isolation from a route (a
FastAPI `Depends` has no meaningful behavior outside a request).

- [ ] **Step 2: Implement the dependencies**

Modify `backend/app/api/deps.py` — replace its entire contents:

```python
from collections.abc import AsyncGenerator

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

DbSession = AsyncSession

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

- [ ] **Step 3: Run the existing suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — `get_session`'s signature and behavior are unchanged, so
no existing route or test is affected; the two new functions are inert
until something calls them (Task 9).

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/deps.py
git commit -m "Добавить зависимости get_current_user и get_current_admin"
```

---

## Task 9: Admin — list/disable/delete users

**Files:**
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/services/user_service.py`
- Create: `backend/app/api/routes/admin.py`
- Modify: `backend/app/main.py`
- Create: `backend/scripts/promote_admin.py`
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: `get_current_admin`, `get_session` (Task 8); `User` (Task 2).
- Produces: `GET /api/admin/users`, `PATCH /api/admin/users/{id}`,
  `DELETE /api/admin/users/{id}` — all requiring `is_admin=True`, all 403
  otherwise; `list_users`, `update_user`, `delete_user` in
  `user_service.py` for anything else that needs them later.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin.py`:

```python
"""Admin: list/disable/delete users, gated behind is_admin."""
from sqlalchemy import update

from app.models.user import User


async def _register(client, email: str) -> dict:
    resp = await client.post("/auth/register", json={"email": email, "password": "hunter22"})
    return resp.json()


async def _make_admin(test_sessionmaker, email: str) -> None:
    async with test_sessionmaker() as session:
        await session.execute(update(User).where(User.email == email).values(is_admin=True))
        await session.commit()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_non_admin_gets_403(client):
    tokens = await _register(client, "plain@example.com")
    resp = await client.get("/admin/users", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 403


async def test_missing_token_gets_401(client):
    resp = await client.get("/admin/users")
    assert resp.status_code == 401


async def test_admin_can_list_users(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin@example.com")
    await _make_admin(test_sessionmaker, "admin@example.com")
    await _register(client, "other@example.com")

    resp = await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert emails == {"admin@example.com", "other@example.com"}
    # never leaks the hash
    assert all("password" not in u for u in resp.json())


async def test_admin_can_disable_a_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin2@example.com")
    await _make_admin(test_sessionmaker, "admin2@example.com")
    target_tokens = await _register(client, "target@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target_id = next(u["id"] for u in users if u["email"] == "target@example.com")

    patch_resp = await client.patch(
        f"/admin/users/{target_id}", json={"is_active": False}, headers=_auth(admin_tokens["access_token"])
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # the disabled user's existing refresh token stops working
    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": target_tokens["refresh_token"]})
    login_resp = await client.post("/auth/login", json={"email": "target@example.com", "password": "hunter22"})
    assert login_resp.status_code == 401


async def test_admin_can_delete_a_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "admin3@example.com")
    await _make_admin(test_sessionmaker, "admin3@example.com")
    await _register(client, "todelete@example.com")

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target_id = next(u["id"] for u in users if u["email"] == "todelete@example.com")

    delete_resp = await client.delete(f"/admin/users/{target_id}", headers=_auth(admin_tokens["access_token"]))
    assert delete_resp.status_code == 204

    remaining = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    assert all(u["id"] != target_id for u in remaining)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_admin.py -v`
Expected: FAIL — 404s (`/admin/users` doesn't exist yet).

- [ ] **Step 3: Create the schemas**

Create `backend/app/schemas/user.py`:

```python
"""Response/request shapes for /api/admin/users — never include
password_hash, deliberately."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    is_active: bool
```

- [ ] **Step 4: Create the service**

Create `backend/app/services/user_service.py`:

```python
"""Admin operations on User rows — list/disable/delete. No self-service
"become admin" path exists by design; see scripts/promote_admin.py for how
the first admin is created."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserUpdate


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def update_user(session: AsyncSession, user_id: int, payload: UserUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
```

- [ ] **Step 5: Create the routes**

Create `backend/app/api/routes/admin.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate
from app.services.user_service import delete_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[UserRead])
async def list_users_route(session: AsyncSession = Depends(get_session)) -> list[User]:
    return await list_users(session)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_route(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
) -> User:
    return await update_user(session, user_id, payload)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(user_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_user(session, user_id)
```

- [ ] **Step 6: Wire it into the app**

Modify `backend/app/main.py` — add `admin` to the routes import
(alphabetical, before `advice`):

```python
from app.api.routes import (
    accounts,
    admin,
    advice,
    assets,
    auth,
    backup,
    ...
)
```

And register it next to the auth router:

```python
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
```

- [ ] **Step 7: Create the first-admin helper script**

Create `backend/scripts/promote_admin.py`:

```python
"""One-off helper to grant admin rights to an existing user by email.

Run it against a running stack with:

    docker compose exec backend python -m scripts.promote_admin someone@example.com

There's no self-service "become admin" path by design (open registration
with no invite codes means anyone could otherwise grant themselves admin)
— this is the only way to create the first admin account.
"""
import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User


async def promote(email: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user with email {email!r}")
            return
        user.is_admin = True
        await session.commit()
        print(f"{email} is now an admin")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_admin <email>")
        sys.exit(1)
    asyncio.run(promote(sys.argv[1]))
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_admin.py -v`
Expected: PASS.

- [ ] **Step 9: Run the whole suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS — everything, old and new.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/user.py backend/app/services/user_service.py \
  backend/app/api/routes/admin.py backend/app/main.py \
  backend/scripts/promote_admin.py backend/tests/test_admin.py
git commit -m "Добавить админку: список/блокировка/удаление пользователей"
```

---

## Task 10: Update UPDATES.md

**Files:**
- Create or modify: `UPDATES.md` (repo root) — **gitignored by design**
  (see the root `.gitignore`'s `# Other` section): this file is the
  project owner's personal local changelog, never pushed to the remote
  repository. Do not `git add` or `git commit` it — doing so would fight
  the `.gitignore` entry that deliberately keeps it out of version
  control.

**Interfaces:** none (documentation only).

- [ ] **Step 1: Record the change**

Per `CLAUDE.md`'s rule to log important new features with date and app
version, append to `UPDATES.md` (create it if it doesn't exist yet — check
first with `ls UPDATES.md`). Read `backend/app/core/config.py`'s
`APP_VERSION` for the current version string before writing the entry.

Add an entry in whatever format the file already uses (if the file is new,
use a simple `## <version> — <date>` heading followed by a bullet list),
e.g.:

```markdown
## 1.2.1 — 2026-09-08

- Добавлена основа мультитенантной аутентификации: регистрация, вход,
  обновление и отзыв токенов (`/api/auth/*`), базовая админка для
  управления пользователями (`/api/admin/users`). Существующие эндпоинты
  (accounts, transactions, ...) пока не защищены и не разделены по
  пользователям — это следующий этап.
```

- [ ] **Step 2: Do not commit this file**

This task has no commit step. `UPDATES.md` stays on disk, untracked —
confirm with `git status` that it shows under untracked/ignored files, not
staged.

---

## Plan Self-Review Notes

- **Spec coverage:** This plan implements the spec's "Auth flow" and
  "Admin" sections in full, plus the `users`/`refresh_tokens` portion of
  "Data model changes". It deliberately defers the spec's "Authorization /
  data isolation", per-user `app_settings`/category seeding, and "Crypto
  price caching" sections to a follow-up plan — see the rationale in this
  plan's **Architecture** section above: those all require adding
  `user_id` to existing domain tables, which is a materially different
  (and much larger) change than standing up new, independent tables. This
  is a deliberate plan split, not a gap.
- **Type/interface consistency:** `TokenPair`, `RegisterRequest`,
  `LoginRequest`, `RefreshRequest` (Task 5) are used with matching field
  names in `auth_service.py` (Task 6), `routes/auth.py` (Task 7), and the
  tests (Task 6, Task 9). `get_current_admin`/`get_current_user` (Task 8)
  are used identically in `routes/admin.py` (Task 9).
- **No placeholders:** every step above contains real, complete code — no
  file in this plan is left partially written.

---

## Next Plan

Once this plan is merged and green, the follow-up plan — **multi-tenant
data isolation** — adds `user_id` to every existing domain table in one
coordinated migration, threads `current_user: User = Depends(get_current_user)`
through every existing router/service (one task per router, each with its
own cross-user isolation test), seeds per-user categories/`app_settings` at
registration (extending `auth_service.register` from this plan), adds the
crypto price cache, retires `AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's
`auth_basic`, and updates `tests/conftest.py`'s shared fixtures (`client`,
`_clean_database`, `account_id`, `categories`) to register/authenticate a
test user instead of relying on instance-wide seeding.
