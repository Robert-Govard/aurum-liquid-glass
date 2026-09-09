# Multi-Tenant Data Isolation — Part 2B (Assets + Crypto) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user's manually-tracked assets and crypto portfolio
private to them. Assets and crypto are one plan, not two, because
`CryptoHolding` is a 1:1 extension of `Asset` (they share a primary key —
`CryptoHolding.asset_id` IS `Asset.id`) — `create_holding` creates an
`Asset` row directly, so scoping `Asset` without also scoping
`crypto_service.py` in the same plan would leave every newly-created
crypto asset with no owner, invisible the moment `routes/assets.py`'s
listing is scoped. This is exactly the "silent invisible row" class of
bug this series has already hit twice (Part 1's `recurring_service`, and
the still-open backup-restore gap) — this plan closes it here instead of
creating a third instance.

**Architecture:** A nullable `user_id` column on six tables: `assets`,
`asset_valuations`, `crypto_portfolios` (missing from the original
spec's table list — a gap noted during this series' very first
brainstorming session, closed here), `crypto_holdings`,
`crypto_transactions`, and `crypto_sync_state` (a global singleton today
— tracks "when did we last refresh prices"; must become one row per user,
or user A opening their crypto tab would mark user B's completely
different coin set as "recently synced" and skip fetching it — the same
class of singleton-to-per-user fix Part 1's Task 11 already made for
`AppSettings`). `routes/assets.py` (no separate service, logic lives in
the route, matching the existing `categories`/`tags` pattern) and
`routes/crypto.py` + `services/crypto_service.py` both get
`current_user: User = Depends(get_current_user)` threaded through every
endpoint, using `scoped()`/`get_owned_or_404()` throughout.

Two of `crypto_service.py`'s three calls to `get_or_create_app_settings`
currently use the `user_id=None` legacy-fallback branch Part 1's Task 11
built specifically so crypto's (until-now-unconverted) calls wouldn't
break — this plan is what finally lets crypto pass its real `user_id`
through, retiring that fallback's last caller. It is not this plan's job
to remove the now-dead fallback branch itself from `settings_service.py`
(that's a small, separate cleanup with no urgency — flagged here, not
required).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2,
httpx (external CoinGecko calls, unchanged by this plan) — same stack as
the rest of this series; no new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-08-multi-tenant-backend-design.md](../specs/2026-09-08-multi-tenant-backend-design.md)

## Global Constraints

- `user_id` is added **nullable** on all six tables, matching this
  series' established precedent (a final NOT NULL pass happens once
  every remaining table is converted, in a later "Part 3" plan).
- Every listing/lookup query against any of the six tables goes through
  `scoped()`/`get_owned_or_404()` (`app/services/scoped.py`, built in
  Part 1) — no hand-written `.where(user_id == ...)`.
- A row that exists but belongs to another user returns 404, not 403.
- `AURUM_COINGECKO_API_KEY` stays a single shared, instance-wide key —
  this plan does not touch how the backend authenticates to CoinGecko,
  only which rows a given sync/read operates over. Two functions,
  `search_coins` and the internal `_fetch_market_data`/`_fetch_90d_change`
  helpers, take no `user_id` at all — they're stateless external-API
  wrappers with nothing to scope.
- `get_or_create_sync_state` and `refresh_prices` become per-user (see
  Architecture above) — this is a required correctness fix, not optional
  polish: without it, one user's tab visit can suppress another user's
  price refresh.
- Known, accepted, unrelated: `tests/test_backup.py`'s two `xfail`-marked
  tests (categories and transactions losing `user_id` on restore,
  deferred to Part 3) are not this plan's concern. If this plan's own
  work exposes a THIRD backup round-trip test failing the same way (e.g.
  one that round-trips assets or crypto data), mark it `xfail` with the
  same reasoning rather than treating it as a regression — but do not
  preemptively mark anything not actually observed failing.
- `net_worth_service.py`, `reports_service.py`, `dashboard_service.py`,
  and `insights_service.py`'s remaining unscoped signals all read `Asset`/
  `AssetValuation` without any `user_id` filter — these are Part 3
  routers, explicitly out of this plan's scope. Once this plan lands,
  those services will aggregate across every user's assets, exactly the
  same class of gap already accepted for `transactions` after Part 2A.
  This is unrelated to isolation for `assets`/`crypto` themselves (a
  user's own asset list, crypto holdings, and crypto history are all
  correctly private after this plan) — it only affects instance-wide
  aggregation views that are already known Part 3 work.

---

## Task 1: Migration — `user_id` on assets and crypto tables

**Files:**
- Create: `backend/alembic/versions/f91a3d5c7e42_add_user_id_to_assets_and_crypto.py`
- Modify: `backend/app/models/asset.py`
- Modify: `backend/app/models/crypto.py`

**Interfaces:**
- Produces: `Asset.user_id`, `AssetValuation.user_id`,
  `CryptoPortfolio.user_id`, `CryptoHolding.user_id`,
  `CryptoTransaction.user_id` — all `Mapped[int | None]`, nullable, FK →
  `users.id` `ondelete="CASCADE"`. `CryptoSyncState.user_id` — same, but
  additionally `unique=True` (one sync-state row per user, same shape as
  `AppSettings.user_id` from Part 1).

- [ ] **Step 1: Add `user_id` to each model**

Modify `backend/app/models/asset.py` — add `ForeignKey` to the existing
`from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text,
UniqueConstraint` import line (already has `ForeignKey`). Add after
`risk_level` in `Asset`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Add after `as_of_date` in `AssetValuation`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Modify `backend/app/models/crypto.py` — `ForeignKey` is already imported.
Add after `is_archived` in `CryptoPortfolio`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Add after `price_change_1y` in `CryptoHolding`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Add after `note` in `CryptoTransaction`:

```python
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
```

Replace `CryptoSyncState`'s whole class body (it currently is a
singleton, `id` always 1 — that concept is retired):

```python
class CryptoSyncState(Base):
    """One row per user — the timestamp of that user's last successful
    CoinGecko price refresh, covering every coin *they* track. A refresh
    always re-prices all of one user's tracked coins in a single batched
    request (see services/crypto_service.py), so there's only ever one
    "last synced" moment to track per user — but it must be per-user, not
    a single shared singleton the way it was before this table had a
    user_id: two different users' coin sets are refreshed independently,
    and a shared timestamp would let one user's tab visit silently
    suppress another user's actual refresh."""

    __tablename__ = "crypto_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Write the migration**

The current head is `e7c4a9f1b620` (Part 2A's `add_user_id_to_transactions`).
Create `backend/alembic/versions/f91a3d5c7e42_add_user_id_to_assets_and_crypto.py`:

```python
"""add user_id to assets, asset_valuations, crypto_portfolios, crypto_holdings, crypto_transactions, crypto_sync_state

Revision ID: f91a3d5c7e42
Revises: e7c4a9f1b620
Create Date: 2026-09-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f91a3d5c7e42'
down_revision: Union[str, None] = 'e7c4a9f1b620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assets', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_assets_user_id', 'assets', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_assets_user_id', 'assets', ['user_id'])

    op.add_column('asset_valuations', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_asset_valuations_user_id', 'asset_valuations', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_asset_valuations_user_id', 'asset_valuations', ['user_id'])

    op.add_column('crypto_portfolios', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_portfolios_user_id', 'crypto_portfolios', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_portfolios_user_id', 'crypto_portfolios', ['user_id'])

    op.add_column('crypto_holdings', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_holdings_user_id', 'crypto_holdings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_holdings_user_id', 'crypto_holdings', ['user_id'])

    op.add_column('crypto_transactions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_transactions_user_id', 'crypto_transactions', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_crypto_transactions_user_id', 'crypto_transactions', ['user_id'])

    op.add_column('crypto_sync_state', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_crypto_sync_state_user_id', 'crypto_sync_state', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_crypto_sync_state_user_id', 'crypto_sync_state', ['user_id'])


def downgrade() -> None:
    op.drop_constraint('uq_crypto_sync_state_user_id', 'crypto_sync_state', type_='unique')
    op.drop_constraint('fk_crypto_sync_state_user_id', 'crypto_sync_state', type_='foreignkey')
    op.drop_column('crypto_sync_state', 'user_id')

    op.drop_index('ix_crypto_transactions_user_id', table_name='crypto_transactions')
    op.drop_constraint('fk_crypto_transactions_user_id', 'crypto_transactions', type_='foreignkey')
    op.drop_column('crypto_transactions', 'user_id')

    op.drop_index('ix_crypto_holdings_user_id', table_name='crypto_holdings')
    op.drop_constraint('fk_crypto_holdings_user_id', 'crypto_holdings', type_='foreignkey')
    op.drop_column('crypto_holdings', 'user_id')

    op.drop_index('ix_crypto_portfolios_user_id', table_name='crypto_portfolios')
    op.drop_constraint('fk_crypto_portfolios_user_id', 'crypto_portfolios', type_='foreignkey')
    op.drop_column('crypto_portfolios', 'user_id')

    op.drop_index('ix_asset_valuations_user_id', table_name='asset_valuations')
    op.drop_constraint('fk_asset_valuations_user_id', 'asset_valuations', type_='foreignkey')
    op.drop_column('asset_valuations', 'user_id')

    op.drop_index('ix_assets_user_id', table_name='assets')
    op.drop_constraint('fk_assets_user_id', 'assets', type_='foreignkey')
    op.drop_column('assets', 'user_id')
```

- [ ] **Step 3: Verify the migration runs both ways**

Run: `docker compose exec backend alembic upgrade head`, then
`docker compose exec backend alembic downgrade -1`, then
`docker compose exec backend alembic upgrade head` again.
Expected: all three succeed, ending at `head`.

- [ ] **Step 4: Run the full test suite**

Run: `docker compose exec backend pytest -v`
Expected: 190 passed, 2 xfailed — unchanged from Part 2A's final state.
Nothing in application code reads the new columns yet.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/f91a3d5c7e42_add_user_id_to_assets_and_crypto.py backend/app/models/asset.py backend/app/models/crypto.py
git commit -m "Добавить nullable user_id в assets, asset_valuations и таблицы крипты"
```

---

## Task 2: Wire `assets`

**Files:**
- Modify: `backend/app/api/routes/assets.py`
- Create: `backend/tests/test_assets.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: no service layer (as before) — later Part 3 work touching
  `Asset`/`AssetValuation` (net worth, reports) must filter by `user_id`
  the same way.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_assets.py` (no test file existed for this
router before):

```python
"""Manually-tracked assets: CRUD, valuation history, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


def _payload(**overrides) -> dict:
    payload = {
        "name": "Vacation House",
        "asset_class": "real_estate",
        "value": "250000.00",
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_asset(client):
    resp = await client.post("/assets", json=_payload())
    assert resp.status_code == 201
    listed = await client.get("/assets")
    assert [a["name"] for a in listed.json()] == ["Vacation House"]


async def test_add_and_list_valuations(client):
    created = (await client.post("/assets", json=_payload())).json()
    await client.post(f"/assets/{created['id']}/valuations", json={"value": "260000.00", "as_of_date": "2026-02-01"})
    valuations = (await client.get(f"/assets/{created['id']}/valuations")).json()
    assert len(valuations) == 2  # the create-time valuation plus this one


async def test_user_a_cannot_see_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb@example.com")
    await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))

    a_assets = (await client.get("/assets")).json()
    assert a_assets == []


async def test_user_a_cannot_update_or_delete_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb2@example.com")
    b_asset = (
        await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert (await client.patch(f"/assets/{b_asset['id']}", json={"name": "Hijacked"})).status_code == 404
    assert (await client.delete(f"/assets/{b_asset['id']}")).status_code == 404


async def test_user_a_cannot_add_or_list_valuations_on_user_bs_asset(client):
    b_tokens = await register_user(client, "assetb3@example.com")
    b_asset = (
        await client.post("/assets", json=_payload(name="B's House"), headers=auth_headers(b_tokens["access_token"]))
    ).json()

    add_resp = await client.post(f"/assets/{b_asset['id']}/valuations", json={"value": "1.00", "as_of_date": "2026-02-01"})
    assert add_resp.status_code == 404

    list_resp = await client.get(f"/assets/{b_asset['id']}/valuations")
    assert list_resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_assets.py -v -k "user_a"`
Expected: FAIL — assets aren't scoped yet.

- [ ] **Step 3: Wire the router**

Modify `backend/app/api/routes/assets.py` — replace the whole file:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_session
from app.models.asset import Asset, AssetValuation
from app.models.user import User
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate, AssetValuationCreate, AssetValuationRead
from app.services.scoped import get_owned_or_404, scoped

router = APIRouter(prefix="/assets", tags=["assets"])

_EAGER = (selectinload(Asset.valuations),)


def _to_read(asset: Asset) -> AssetRead:
    latest = asset.valuations[-1] if asset.valuations else None
    return AssetRead(
        id=asset.id,
        name=asset.name,
        asset_class=asset.asset_class,
        currency=asset.currency,
        notes=asset.notes,
        capital_role=asset.capital_role,
        monthly_cash_flow=asset.monthly_cash_flow,
        risk_level=asset.risk_level,
        current_value=latest.value if latest else 0,
        as_of_date=latest.as_of_date if latest else asset.created_at.date(),
    )


@router.get("", response_model=list[AssetRead])
async def list_assets(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)
) -> list[AssetRead]:
    stmt = scoped(select(Asset), Asset, current_user.id).options(*_EAGER).order_by(Asset.name)
    result = await session.execute(stmt)
    return [_to_read(asset) for asset in result.scalars().all()]


@router.post("", response_model=AssetRead, status_code=201)
async def create_asset(
    payload: AssetCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetRead:
    asset = Asset(
        name=payload.name,
        asset_class=payload.asset_class,
        currency=payload.currency,
        notes=payload.notes,
        capital_role=payload.capital_role,
        monthly_cash_flow=payload.monthly_cash_flow,
        risk_level=payload.risk_level,
        user_id=current_user.id,
    )
    session.add(asset)
    await session.flush()
    session.add(
        AssetValuation(
            asset_id=asset.id, value=payload.value, as_of_date=payload.as_of_date, user_id=current_user.id
        )
    )
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset.id))
    return _to_read(refreshed.scalar_one())


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetRead:
    result = await session.execute(
        scoped(select(Asset), Asset, current_user.id).where(Asset.id == asset_id).options(*_EAGER)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Asset not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await session.commit()
    await session.refresh(asset, attribute_names=["valuations"])
    return _to_read(asset)


@router.post("/{asset_id}/valuations", response_model=AssetRead)
async def add_asset_valuation(
    asset_id: int,
    payload: AssetValuationCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AssetRead:
    """Records (or corrects) an asset's value as of a date. Re-submitting the
    same date updates that day's value instead of erroring, so users can fix
    a typo without needing a separate edit flow."""
    await get_owned_or_404(session, Asset, asset_id, current_user.id, detail="Asset not found")

    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(asset_id=asset_id, value=payload.value, as_of_date=payload.as_of_date, user_id=current_user.id)
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={"value": payload.value},
        )
    )
    await session.execute(upsert_stmt)
    await session.commit()

    refreshed = await session.execute(select(Asset).options(*_EAGER).where(Asset.id == asset_id))
    return _to_read(refreshed.scalar_one())


@router.get("/{asset_id}/valuations", response_model=list[AssetValuationRead])
async def list_asset_valuations(
    asset_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AssetValuation]:
    await get_owned_or_404(session, Asset, asset_id, current_user.id, detail="Asset not found")
    result = await session.execute(
        select(AssetValuation).where(AssetValuation.asset_id == asset_id).order_by(AssetValuation.as_of_date)
    )
    return list(result.scalars().all())


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    asset = await get_owned_or_404(session, Asset, asset_id, current_user.id, detail="Asset not found")
    await session.delete(asset)
    await session.commit()
```

(`update_asset` imports `HTTPException` locally rather than at module
level purely because the rest of the file no longer needs it at
module scope after switching to `get_owned_or_404` everywhere else —
if you find that awkward, move `from fastapi import HTTPException` up
to the top-level import line instead; either is fine, just don't leave
two different import styles for the same name in one file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_assets.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, plus the 2 known `xfail`s — no new failures. (The
existing `test_holding_shows_up_in_net_worth_breakdown` test in
`test_crypto.py` hits `/net-worth/summary`, an unscoped Part 3 router
that reads every `Asset` regardless of owner — it will keep passing
unchanged, since it doesn't filter by user at all yet.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/assets.py backend/tests/test_assets.py
git commit -m "Изолировать assets по пользователю"
```

---

## Task 3: Wire crypto portfolios

**Files:**
- Modify: `backend/app/services/crypto_service.py`
- Modify: `backend/app/api/routes/crypto.py`
- Create: `backend/tests/test_crypto_portfolios.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`.
- Produces: `list_portfolios(session, user_id, include_archived)`,
  `create_portfolio(session, payload, user_id)`,
  `update_portfolio(session, portfolio_id, payload, user_id)`,
  `delete_portfolio(session, portfolio_id, user_id)`,
  `get_or_create_default_portfolio(session, user_id)` — this last one is
  consumed by Task 4's `create_holding`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_crypto_portfolios.py` (kept separate from the
much larger `test_crypto.py` — portfolios are their own concern with no
CoinGecko interaction to monkeypatch):

```python
"""Crypto portfolios: CRUD, plus per-user isolation."""
from tests.helpers import auth_headers, register_user


async def test_create_and_list_portfolio(client):
    resp = await client.post("/crypto/portfolios", json={"name": "Long-term"})
    assert resp.status_code == 201
    listed = await client.get("/crypto/portfolios")
    assert [p["name"] for p in listed.json()] == ["Long-term"]


async def test_user_a_cannot_see_user_bs_portfolio(client):
    b_tokens = await register_user(client, "portb@example.com")
    await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))

    a_portfolios = (await client.get("/crypto/portfolios")).json()
    assert a_portfolios == []


async def test_user_a_cannot_update_or_delete_user_bs_portfolio(client):
    b_tokens = await register_user(client, "portb2@example.com")
    b_portfolio = (
        await client.post("/crypto/portfolios", json={"name": "B's"}, headers=auth_headers(b_tokens["access_token"]))
    ).json()

    assert (await client.patch(f"/crypto/portfolios/{b_portfolio['id']}", json={"name": "Hijacked"})).status_code == 404
    assert (await client.delete(f"/crypto/portfolios/{b_portfolio['id']}")).status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_crypto_portfolios.py -v -k user_a`
Expected: FAIL.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/crypto_service.py`. Add to the existing
`from app.services.settings_service import get_or_create_app_settings`
import line's block (add a new import line right after it):

```python
from app.services.scoped import get_owned_or_404, scoped
```

Replace `list_portfolios`:

```python
async def list_portfolios(session: AsyncSession, user_id: int, include_archived: bool) -> list[CryptoPortfolioRead]:
    stmt = scoped(select(CryptoPortfolio), CryptoPortfolio, user_id).order_by(CryptoPortfolio.id)
    if not include_archived:
        stmt = stmt.where(CryptoPortfolio.is_archived.is_(False))
    portfolios = (await session.execute(stmt)).scalars().all()
    return [_portfolio_to_read(p) for p in portfolios]
```

Replace `get_or_create_default_portfolio`:

```python
async def get_or_create_default_portfolio(session: AsyncSession, user_id: int) -> CryptoPortfolio:
    """The portfolio a new holding lands in when the caller doesn't specify
    one (see CryptoHoldingCreate.portfolio_id) — this user's earliest-created
    portfolio, auto-created the first time it's needed. Same self-healing
    "create on first use" shape as seed_default_app_settings: a portfolio can
    later be deleted once empty (see delete_portfolio), so this can't just
    assume any particular row always exists."""
    existing = (
        await session.execute(scoped(select(CryptoPortfolio), CryptoPortfolio, user_id).order_by(CryptoPortfolio.id).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    portfolio = CryptoPortfolio(name="Main Portfolio", color=PORTFOLIO_PALETTE[0], user_id=user_id)
    session.add(portfolio)
    await session.flush()
    return portfolio
```

Replace `create_portfolio`:

```python
async def create_portfolio(session: AsyncSession, payload: CryptoPortfolioCreate, user_id: int) -> CryptoPortfolioRead:
    count = (await session.execute(scoped(select(CryptoPortfolio.id), CryptoPortfolio, user_id))).scalars().all()
    color = PORTFOLIO_PALETTE[len(count) % len(PORTFOLIO_PALETTE)]
    portfolio = CryptoPortfolio(name=payload.name, color=color, user_id=user_id)
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    return _portfolio_to_read(portfolio)
```

Replace `update_portfolio` and `delete_portfolio`:

```python
async def update_portfolio(
    session: AsyncSession, portfolio_id: int, payload: CryptoPortfolioUpdate, user_id: int
) -> CryptoPortfolioRead:
    portfolio = await get_owned_or_404(session, CryptoPortfolio, portfolio_id, user_id, detail="Crypto portfolio not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portfolio, field, value)
    await session.commit()
    await session.refresh(portfolio)
    return _portfolio_to_read(portfolio)


async def delete_portfolio(session: AsyncSession, portfolio_id: int, user_id: int) -> None:
    portfolio = await get_owned_or_404(session, CryptoPortfolio, portfolio_id, user_id, detail="Crypto portfolio not found")
    has_holding = (
        await session.execute(select(CryptoHolding.asset_id).where(CryptoHolding.portfolio_id == portfolio_id).limit(1))
    ).first()
    if has_holding is not None:
        raise HTTPException(status_code=400, detail="Move or delete its coins before deleting a portfolio")
    await session.delete(portfolio)
    await session.commit()
```

(The `has_holding` check stays unfiltered by user — same "globally
unique id" reasoning used throughout this series: `portfolio_id` was
just confirmed owned by `get_owned_or_404` above, and once Task 4 makes
`create_holding` only ever attach a holding to a portfolio it already
verified the caller owns, a holding pointing at this `portfolio_id` can
only ever belong to the same user.)

- [ ] **Step 4: Wire the routes**

Modify `backend/app/api/routes/crypto.py` — add to the existing imports:

```python
from app.api.deps import get_current_user, get_session
from app.models.user import User
```

(Merge with the existing `from app.api.deps import get_session` line.)
Replace the four portfolio route handlers:

```python
@router.get("/portfolios", response_model=list[CryptoPortfolioRead])
async def read_portfolios(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CryptoPortfolioRead]:
    return await list_portfolios(session, current_user.id, include_archived)


@router.post("/portfolios", response_model=CryptoPortfolioRead, status_code=201)
async def create_portfolio_route(
    payload: CryptoPortfolioCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoPortfolioRead:
    return await create_portfolio(session, payload, current_user.id)


@router.patch("/portfolios/{portfolio_id}", response_model=CryptoPortfolioRead)
async def update_portfolio_route(
    portfolio_id: int,
    payload: CryptoPortfolioUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoPortfolioRead:
    return await update_portfolio(session, portfolio_id, payload, current_user.id)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def delete_portfolio_route(
    portfolio_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_portfolio(session, portfolio_id, current_user.id)
```

Do NOT touch any of the other route handlers in this file yet (holdings,
transactions, history, performance, search) — those are Task 4 and
Task 5. This task's diff to `routes/crypto.py` is exactly these four
handlers plus the two new import lines.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_crypto_portfolios.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: `test_crypto.py`'s existing tests will FAIL at this point —
they call `/crypto/holdings`, whose underlying `create_holding`/
`list_holdings`/`refresh_prices` still call the now-changed
`get_or_create_default_portfolio(session, user_id)` and
`list_portfolios`/`create_portfolio` with the OLD (no-`user_id`)
signature from other, not-yet-updated functions in this same file. This
is expected — Task 4 fixes the remaining functions in
`crypto_service.py` that call into what this task just changed. Confirm
the failures are confined to `test_crypto.py` (not `test_assets.py`,
`test_crypto_portfolios.py`, or anything else), and report the exact
failure list — if anything outside `test_crypto.py` fails, that's a
real regression to investigate before committing.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/crypto_service.py backend/app/api/routes/crypto.py backend/tests/test_crypto_portfolios.py
git commit -m "Изолировать crypto-портфели по пользователю"
```

---

## Task 4: Wire crypto holdings, transactions, and price sync

**Files:**
- Modify: `backend/app/services/crypto_service.py`
- Modify: `backend/app/api/routes/crypto.py`
- Modify: `backend/tests/test_crypto.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `get_owned_or_404`,
  `get_or_create_default_portfolio(session, user_id)` (Task 3).
- Produces: `list_holdings(session, user_id, portfolio_id=None)`,
  `get_or_create_sync_state(session, user_id)`,
  `refresh_prices(session, user_id, *, force, portfolio_id=None)`,
  `create_holding(session, payload, user_id)`,
  `add_transaction(session, asset_id, payload, user_id)`,
  `update_transaction(session, transaction_id, payload, user_id)`,
  `delete_transaction(session, transaction_id, user_id)`,
  `list_transactions(session, asset_id, user_id)`.

- [ ] **Step 1: Update `test_crypto.py`'s helper functions and fix the tests Task 3 left red**

This is the one place in this plan that touches an existing test file's
*helpers*, not just appending new tests — because every existing test in
this file goes through `_add_bitcoin`, which posts to `/crypto/holdings`.
No new isolation-specific helper is needed (the file already imports
`auth_headers`/`register_user` indirectly through `tests/helpers`, and
the `client` fixture is already authenticated) — the existing tests need
no changes themselves, only the production code they call. Do not modify
any existing test function's body or assertions in this step; that
happens implicitly once Step 2 below makes them pass again.

- [ ] **Step 2: Wire the service**

Modify `backend/app/services/crypto_service.py`.

Replace `_get_holding_or_404`:

```python
async def _get_holding_or_404(session: AsyncSession, asset_id: int, user_id: int) -> CryptoHolding:
    result = await session.execute(
        scoped(select(CryptoHolding), CryptoHolding, user_id).options(*_EAGER).where(CryptoHolding.asset_id == asset_id)
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=404, detail="Crypto holding not found")
    return holding
```

Replace `get_or_create_sync_state`:

```python
async def get_or_create_sync_state(session: AsyncSession, user_id: int) -> CryptoSyncState:
    result = await session.execute(select(CryptoSyncState).where(CryptoSyncState.user_id == user_id))
    state = result.scalar_one_or_none()
    if state is None:
        state = CryptoSyncState(user_id=user_id, last_synced_at=None)
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state
```

Replace `_upsert_valuation`'s signature and body to stamp `user_id`:

```python
async def _upsert_valuation(session: AsyncSession, asset_id: int, value: Decimal, as_of_date: date_, user_id: int) -> None:
    """Same upsert-by-date pattern as routes/assets.py's POST
    /assets/{id}/valuations — re-syncing the same day updates that day's
    value instead of erroring. Still needed even though quantity/price
    aren't stored on CryptoHolding: Net Worth's whole engine reads this
    table, not CryptoHolding, for a coin's value history."""
    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(asset_id=asset_id, value=value, as_of_date=as_of_date, user_id=user_id)
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={"value": value},
        )
    )
    await session.execute(upsert_stmt)
```

Replace `list_holdings`:

```python
async def list_holdings(session: AsyncSession, user_id: int, portfolio_id: int | None = None) -> list[CryptoHolding]:
    stmt = scoped(select(CryptoHolding), CryptoHolding, user_id).options(*_EAGER).order_by(CryptoHolding.name)
    if portfolio_id is not None:
        stmt = stmt.where(CryptoHolding.portfolio_id == portfolio_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

Replace `refresh_prices` — every `_upsert_valuation(...)` call inside it
gains a trailing `, user_id` argument, `get_or_create_sync_state`/
`list_holdings`/`get_or_create_app_settings` all gain `user_id`, and the
signature itself gains the parameter:

```python
async def refresh_prices(
    session: AsyncSession, user_id: int, *, force: bool, portfolio_id: int | None = None
) -> CryptoSyncResult:
    """Sync always covers every one of this user's holdings regardless of
    `portfolio_id` — a stale price on a coin the user isn't currently
    looking at would still be wrong the next time they switch tabs.
    `portfolio_id` only narrows what's returned in the response's
    `holdings` list, for the Crypto tab's portfolio filter."""
    state = await get_or_create_sync_state(session, user_id)
    now = datetime.now(timezone.utc)

    if not force and state.last_synced_at is not None and now - state.last_synced_at < AUTO_REFRESH_INTERVAL:
        holdings = await list_holdings(session, user_id, portfolio_id)
        return CryptoSyncResult(
            synced=False, last_synced_at=state.last_synced_at, holdings=_sort_by_invested([_to_read(h) for h in holdings])
        )

    holdings = await list_holdings(session, user_id)
    error_key: Literal["unreachable"] | None = None
    if holdings:
        settings = await get_or_create_app_settings(session, user_id)
        try:
            market_data = await _fetch_market_data([h.coingecko_id for h in holdings], settings.currency.lower())
        except httpx.HTTPError:
            # CoinGecko down/rate-limited — don't touch last_synced_at (the
            # next open of the tab retries) and don't touch any existing
            # price/AssetValuation. The tab still shows the last known
            # values instead of an empty/broken page over an external outage.
            error_key = "unreachable"
        else:
            today = date_.today()
            for holding in holdings:
                point = market_data.get(holding.coingecko_id)
                if point is None:
                    continue  # coin missing from the response — keep its last known values, don't zero them out
                holding.last_price = point.price
                holding.price_change_1h = point.change_1h
                holding.price_change_24h = point.change_24h
                holding.price_change_7d = point.change_7d
                holding.price_change_30d = point.change_30d
                holding.price_change_1y = point.change_1y
                quantity, _ = _compute_position(holding.transactions)
                if quantity > 0:
                    await _upsert_valuation(session, holding.asset_id, quantity * point.price, today, user_id)

    if error_key is None:
        state.last_synced_at = now
    await session.commit()

    # holdings were mutated in place above (ordinary ORM attribute
    # assignment, not a raw Core write) — no need to re-query, they already
    # reflect what was just committed.
    visible = holdings if portfolio_id is None else [h for h in holdings if h.portfolio_id == portfolio_id]
    return CryptoSyncResult(
        synced=error_key is None,
        last_synced_at=state.last_synced_at,
        error_key=error_key,
        holdings=_sort_by_invested([_to_read(h) for h in visible]),
    )
```

Replace `create_holding`:

```python
async def create_holding(session: AsyncSession, payload: CryptoHoldingCreate, user_id: int) -> CryptoHoldingRead:
    settings = await get_or_create_app_settings(session, user_id)

    if payload.portfolio_id is not None:
        portfolio = await get_owned_or_404(session, CryptoPortfolio, payload.portfolio_id, user_id, detail="Crypto portfolio not found")
        portfolio_id = portfolio.id
    else:
        portfolio_id = (await get_or_create_default_portfolio(session, user_id)).id

    asset = Asset(
        name=payload.name,
        asset_class=AssetClass.CRYPTO,
        currency=settings.currency,
        capital_role=CapitalRole.NEUTRAL,
        # Defaults to HIGH, not the Asset model's own MEDIUM default — matches
        # this app's own risk-level copy, which names crypto as the textbook
        # HIGH example (see lib/i18n.ts's netWorth.riskLevelFormHint.high).
        risk_level=RiskLevel.HIGH,
        user_id=user_id,
    )
    session.add(asset)
    await session.flush()

    holding = CryptoHolding(
        asset_id=asset.id,
        portfolio_id=portfolio_id,
        coingecko_id=payload.coingecko_id,
        symbol=payload.symbol.upper(),
        name=payload.name,
        thumb_url=payload.thumb_url,
        user_id=user_id,
    )
    session.add(holding)

    holding.transactions.append(
        CryptoTransaction(
            type=CryptoTransactionType.BUY,
            quantity=payload.quantity,
            price_per_unit=payload.price_per_unit,
            date=payload.date,
            note=payload.note,
            user_id=user_id,
        )
    )
    await session.flush()

    # Seed today's live price immediately — a coin the user just added
    # sitting at "no price yet" until tomorrow's auto-sync would be
    # confusing, and this one call is clearly justified by an explicit
    # user action.
    try:
        market_data = await _fetch_market_data([payload.coingecko_id], settings.currency.lower())
        point = market_data.get(payload.coingecko_id)
        if point is not None:
            holding.last_price = point.price
            holding.price_change_1h = point.change_1h
            holding.price_change_24h = point.change_24h
            holding.price_change_7d = point.change_7d
            holding.price_change_30d = point.change_30d
            holding.price_change_1y = point.change_1y
            await _upsert_valuation(session, asset.id, payload.quantity * point.price, date_.today(), user_id)
        # This counts as a real sync — bump the shared timestamp so the next
        # GET /crypto/holdings doesn't immediately re-fetch every holding
        # again a moment later (see refresh_prices' 24h window).
        state = await get_or_create_sync_state(session, user_id)
        state.last_synced_at = datetime.now(timezone.utc)
    except httpx.HTTPError:
        pass  # holding is still created — the next daily/manual sync will price it

    await session.commit()
    return _to_read(holding)
```

Replace `add_transaction`:

```python
async def add_transaction(
    session: AsyncSession, asset_id: int, payload: CryptoTransactionCreate, user_id: int
) -> CryptoHoldingRead:
    """A buy or sell against an existing holding — never calls CoinGecko
    (see module docstring): value is recomputed from the last cached
    price, same principle as the old quantity-only edit it replaces."""
    holding = await _get_holding_or_404(session, asset_id, user_id)

    if payload.type == CryptoTransactionType.SELL:
        current_quantity, _ = _compute_position(holding.transactions)
        if payload.quantity > current_quantity:
            raise HTTPException(status_code=400, detail="Cannot sell more than you currently hold")

    holding.transactions.append(
        CryptoTransaction(
            type=payload.type,
            quantity=payload.quantity,
            price_per_unit=payload.price_per_unit,
            date=payload.date,
            note=payload.note,
            user_id=user_id,
        )
    )
    await session.flush()

    quantity, _ = _compute_position(holding.transactions)
    if holding.last_price is not None:
        await _upsert_valuation(session, asset_id, quantity * holding.last_price, date_.today(), user_id)

    await session.commit()
    return _to_read(holding)
```

Replace `update_transaction`:

```python
async def update_transaction(
    session: AsyncSession, transaction_id: int, payload: CryptoTransactionUpdate, user_id: int
) -> CryptoHoldingRead:
    """Edit an existing buy/sell entry — the "view/edit a transaction" flow
    a plain delete-and-recreate can't offer (you'd lose the original id and
    any history a future feature might key off it). Never calls CoinGecko,
    same as add_transaction: value is recomputed from the last cached price."""
    transaction = await get_owned_or_404(session, CryptoTransaction, transaction_id, user_id, detail="Crypto transaction not found")
    asset_id = transaction.asset_id
    holding = await _get_holding_or_404(session, asset_id, user_id)

    updates = payload.model_dump(exclude_unset=True)
    effective_type = updates.get("type", transaction.type)
    effective_quantity = updates.get("quantity", transaction.quantity)

    if effective_type == CryptoTransactionType.SELL:
        # Same guard as add_transaction, checked against every *other*
        # transaction on this holding — editing this one in place must not
        # let it sell more than what the rest of the log would leave held.
        others = [t for t in holding.transactions if t.id != transaction_id]
        quantity_without_this, _ = _compute_position(others)
        if effective_quantity > quantity_without_this:
            raise HTTPException(status_code=400, detail="Cannot sell more than you currently hold")

    for field, value in updates.items():
        setattr(transaction, field, value)
    await session.flush()

    quantity, _ = _compute_position(holding.transactions)
    if holding.last_price is not None:
        await _upsert_valuation(session, asset_id, quantity * holding.last_price, date_.today(), user_id)

    await session.commit()
    return _to_read(holding)
```

Replace `list_transactions`:

```python
async def list_transactions(session: AsyncSession, asset_id: int, user_id: int) -> list[CryptoTransaction]:
    await _get_holding_or_404(session, asset_id, user_id)  # 404s if the holding itself doesn't exist or isn't the caller's
    result = await session.execute(
        scoped(select(CryptoTransaction), CryptoTransaction, user_id)
        .where(CryptoTransaction.asset_id == asset_id)
        .order_by(CryptoTransaction.date.desc(), CryptoTransaction.id.desc())
    )
    return list(result.scalars().all())
```

Replace `delete_transaction`:

```python
async def delete_transaction(session: AsyncSession, transaction_id: int, user_id: int) -> None:
    transaction = await get_owned_or_404(session, CryptoTransaction, transaction_id, user_id, detail="Crypto transaction not found")
    asset_id = transaction.asset_id
    await session.delete(transaction)
    await session.flush()

    holding = await _get_holding_or_404(session, asset_id, user_id)
    quantity, _ = _compute_position(holding.transactions)
    if holding.last_price is not None:
        await _upsert_valuation(session, asset_id, quantity * holding.last_price, date_.today(), user_id)

    await session.commit()
```

- [ ] **Step 3: Wire the routes**

Modify `backend/app/api/routes/crypto.py` — replace the holdings and
transactions route handlers (leave the portfolio handlers from Task 3,
and the search/history/performance handlers for Task 5, untouched):

```python
@router.get("/holdings", response_model=CryptoSyncResult)
async def read_holdings(
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoSyncResult:
    """Opening the Crypto tab lands here — this is also where the lazy
    once-a-day auto-refresh happens (see services/crypto_service.py):
    prices only actually get re-fetched from CoinGecko if 24h have passed
    since the last sync, otherwise this just reads the current cache."""
    return await refresh_prices(session, current_user.id, force=False, portfolio_id=portfolio_id)


@router.post("/refresh", response_model=CryptoSyncResult)
async def refresh_holdings(
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoSyncResult:
    """The "Refresh prices" button — always hits CoinGecko regardless of
    the once-a-day window."""
    return await refresh_prices(session, current_user.id, force=True, portfolio_id=portfolio_id)


@router.post("/holdings", response_model=CryptoHoldingRead, status_code=201)
async def create_holding_route(
    payload: CryptoHoldingCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoHoldingRead:
    return await create_holding(session, payload, current_user.id)


@router.post("/holdings/{asset_id}/transactions", response_model=CryptoHoldingRead, status_code=201)
async def add_transaction_route(
    asset_id: int,
    payload: CryptoTransactionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoHoldingRead:
    """Buy more of, or sell some of, a coin already being tracked."""
    return await add_transaction(session, asset_id, payload, current_user.id)


@router.get("/holdings/{asset_id}/transactions", response_model=list[CryptoTransactionRead])
async def list_transactions_route(
    asset_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CryptoTransactionRead]:
    return await list_transactions(session, asset_id, current_user.id)


@router.patch("/transactions/{transaction_id}", response_model=CryptoHoldingRead)
async def update_transaction_route(
    transaction_id: int,
    payload: CryptoTransactionUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoHoldingRead:
    return await update_transaction(session, transaction_id, payload, current_user.id)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction_route(
    transaction_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await delete_transaction(session, transaction_id, current_user.id)
```

- [ ] **Step 4: Run `test_crypto.py` and `test_crypto_portfolios.py`**

Run: `docker compose exec backend pytest tests/test_crypto.py tests/test_crypto_portfolios.py -v`
Expected: PASS — all pre-existing `test_crypto.py` tests (which needed
no code changes themselves, per Step 1) pass again now that the
production code they call accepts and threads `user_id` correctly.

- [ ] **Step 5: Add isolation tests for holdings and transactions**

Append to `backend/tests/test_crypto.py`:

```python
from tests.helpers import auth_headers, register_user


async def test_user_a_cannot_see_user_bs_holdings(client, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    b_tokens = await register_user(client, "cryptob@example.com")
    await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "1",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
        headers=auth_headers(b_tokens["access_token"]),
    )

    a_holdings = (await client.get("/crypto/holdings")).json()["holdings"]
    assert a_holdings == []


async def test_user_a_cannot_transact_against_or_delete_user_bs_holding(client, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    b_tokens = await register_user(client, "cryptob2@example.com")

    b_resp = await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "1",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
        headers=auth_headers(b_tokens["access_token"]),
    )
    b_asset_id = b_resp.json()["asset_id"]

    add_txn_resp = await client.post(
        f"/crypto/holdings/{b_asset_id}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "1", "date": "2026-01-02"},
    )
    assert add_txn_resp.status_code == 404

    list_txn_resp = await client.get(f"/crypto/holdings/{b_asset_id}/transactions")
    assert list_txn_resp.status_code == 404
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_crypto.py -v`
Expected: PASS — all tests in the file, old and new.

- [ ] **Step 7: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, plus the 2 known `xfail`s.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/crypto_service.py backend/app/api/routes/crypto.py backend/tests/test_crypto.py
git commit -m "Изолировать crypto holdings, транзакции и синхронизацию цен по пользователю"
```

---

## Task 5: Wire crypto history and 90-day performance

**Files:**
- Modify: `backend/app/services/crypto_service.py`
- Modify: `backend/app/api/routes/crypto.py`
- Modify: `backend/tests/test_crypto.py`

**Interfaces:**
- Consumes: `get_current_user`, `scoped`, `list_holdings(session, user_id, portfolio_id=None)` (Task 4).
- Produces: `get_crypto_history(session, range_key, user_id, portfolio_id=None)`,
  `get_90d_performance(session, user_id, portfolio_id)`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_crypto.py`:

```python
async def test_crypto_history_only_counts_the_callers_own_holdings(client, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "1", "40000")

    b_tokens = await register_user(client, "cryptob3@example.com")
    await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "10",
            "price_per_unit": "1",
            "date": "2026-01-01",
        },
        headers=auth_headers(b_tokens["access_token"]),
    )

    a_history = (await client.get("/crypto/history", params={"range": "30d"})).json()
    assert money(a_history["current"]) == money("50000")  # only A's 1 BTC, not B's 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_crypto.py -v -k test_crypto_history_only_counts_the_callers_own_holdings`
Expected: FAIL — `get_crypto_history` currently sums every user's crypto
assets together, so `current` would include both A's and B's holdings.

- [ ] **Step 3: Wire the service**

Modify `backend/app/services/crypto_service.py`. Replace
`get_crypto_history`'s signature and its first query:

```python
async def get_crypto_history(
    session: AsyncSession, range_key: str, user_id: int, portfolio_id: int | None = None
) -> CryptoHistoryResponse:
    """Total crypto holdings value over time, for the History chart on the
    Crypto tab. Same "cumulative point events, forward-filled" approach as
    net_worth_service.py's own asset series — duplicated here rather than
    imported, so this can't destabilize the already-tested Net Worth engine,
    and scoped to this user's crypto-class assets only (a deleted holding's
    AssetValuation rows are gone via cascade, so its history naturally
    drops out here too, same as it already does for Net Worth). Further
    scoped to one portfolio's assets when `portfolio_id` is given, for the
    Crypto tab's portfolio filter."""
    today = date_.today()

    asset_stmt = (
        scoped(select(Asset.id), Asset, user_id)
        .join(CryptoHolding, CryptoHolding.asset_id == Asset.id)
        .where(Asset.asset_class == AssetClass.CRYPTO)
    )
    if portfolio_id is not None:
        asset_stmt = asset_stmt.where(CryptoHolding.portfolio_id == portfolio_id)
    crypto_asset_ids = set((await session.execute(asset_stmt)).scalars().all())
    if not crypto_asset_ids:
        return CryptoHistoryResponse(range=range_key, current=Decimal("0"), change_amount=Decimal("0"), change_percent=None, series=[])

    valuations = (
        await session.execute(
            select(AssetValuation.asset_id, AssetValuation.as_of_date, AssetValuation.value)
            .where(AssetValuation.asset_id.in_(crypto_asset_ids))
            .order_by(AssetValuation.as_of_date)
        )
    ).all()
```

(Everything from `if not valuations:` through the end of the function is
unchanged — leave it exactly as it is. The safety of the unfiltered
`AssetValuation.asset_id.in_(crypto_asset_ids)` query below it holds
precisely because `crypto_asset_ids` is now already scoped to this
user's own assets by the `scoped()` call above it.)

Replace `get_90d_performance`'s signature and its `settings` call:

```python
async def get_90d_performance(session: AsyncSession, user_id: int, portfolio_id: int | None) -> CryptoPerformanceResponse:
    """Real 90-day % price change per currently-held coin, for the Crypto
    tab's Best/Worst Performer stat when the 90d range is picked. Unlike
    1h/24h/7d/30d/1y (all one field on the same batched /coins/markets sync
    call, see _fetch_market_data), CoinGecko has no 90-day window on that
    endpoint at all — the only way to get it is one market_chart call per
    coin, so this is deliberately never part of the regular sync and only
    ever runs on an explicit "look at 90d" user action, same justification
    as the seed fetch on adding a new holding. Bounded concurrency (5 at
    once) keeps a big portfolio from firing dozens of requests in the same
    instant."""
    holdings = await list_holdings(session, user_id, portfolio_id)
    held = [h for h in holdings if _compute_position(h.transactions)[0] > 0]
    if not held:
        return CryptoPerformanceResponse(items=[])

    settings = await get_or_create_app_settings(session, user_id)
    api_key = _require_api_key()
    semaphore = asyncio.Semaphore(5)

    async def fetch_one(client: httpx.AsyncClient, holding: CryptoHolding) -> CryptoPerformancePoint:
        async with semaphore:
            change = await _fetch_90d_change(client, api_key, holding.coingecko_id, settings.currency.lower())
        return CryptoPerformancePoint(asset_id=holding.asset_id, price_change_percent=change)

    async with httpx.AsyncClient(timeout=10.0) as client:
        items = await asyncio.gather(*(fetch_one(client, h) for h in held))
    return CryptoPerformanceResponse(items=list(items))
```

- [ ] **Step 4: Wire the routes**

Modify `backend/app/api/routes/crypto.py` — replace the history and
90d-performance route handlers (the `search` handler is left completely
untouched — it takes no `user_id` at all, per this plan's Global
Constraints):

```python
@router.get("/history", response_model=CryptoHistoryResponse)
async def read_crypto_history(
    range: str = Query(default="30d", pattern=_HISTORY_RANGE_PATTERN),
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoHistoryResponse:
    return await get_crypto_history(session, range, current_user.id, portfolio_id)


@router.get("/performance/90d", response_model=CryptoPerformanceResponse)
async def read_90d_performance(
    portfolio_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CryptoPerformanceResponse:
    """Backs the Best/Worst Performer stat only while the 90d range is
    selected — see get_90d_performance's docstring for why this is a
    separate on-demand call instead of a cached field like 7d/30d/1y."""
    return await get_90d_performance(session, current_user.id, portfolio_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_crypto.py -v`
Expected: PASS — every test in the file.

- [ ] **Step 6: Run the full suite**

Run: `docker compose exec backend pytest -v`
Expected: PASS, plus the 2 known `xfail`s — this is the last task in
this plan, so this run should show the whole suite green (modulo the two
accepted `xfail`s) with no `user_id`-related warnings anywhere in
`assets`/`crypto`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/crypto_service.py backend/app/api/routes/crypto.py backend/tests/test_crypto.py
git commit -m "Изолировать историю и 90-дневную доходность крипто-портфеля по пользователю"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Implements the "Authorization / data isolation"
  approach for `assets`, `asset_valuations`, and all four crypto tables
  (`crypto_portfolios` — a genuine spec-list gap, closed here — plus
  `crypto_holdings`, `crypto_transactions`, `crypto_sync_state`, the last
  of which the spec didn't anticipate needing scoping at all since it
  predates the "one global sync timestamp is now wrong" realization this
  plan documents). `CryptoSyncState`'s singleton-to-per-user fix mirrors
  Part 1's `AppSettings` fix exactly, for the same underlying reason.
- **Type/interface consistency:** every service function's new `user_id:
  int` parameter is threaded consistently between its route and its
  tests, matching the naming/position convention from every prior plan
  in this series. `scoped()`/`get_owned_or_404()` usage matches exactly.
- **No placeholders:** every step contains complete, real code.

---

## Next Plan

**Part 3 (read-only aggregation + cutover):** wires `dashboard`,
`net_worth`, `cash_flow`, `reports`, `advice`, and finishes converting
`insights_service.py`'s remaining unscoped signals; reworks
`backup_service.py` to be fully per-user (closing the `xfail`-marked
categories/transactions restore gaps, and whatever the same issue turns
out to affect for assets/crypto once this plan lands); runs the final
migration flipping every `user_id` column added across Parts 1, 2A, and
2B to `NOT NULL`; retires `AURUM_BASIC_AUTH_USER`/`PASSWORD` and nginx's
`auth_basic`; and — flagged by this plan, not required by it — removes
`settings_service.py`'s now-fully-unused `user_id=None` legacy-fallback
branch, since this plan's Task 4 was its last remaining caller.
