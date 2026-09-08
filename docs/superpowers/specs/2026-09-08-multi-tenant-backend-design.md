# Multi-tenant backend — design

Date: 2026-09-08
Status: approved for planning

## Context

Aurum currently ships as a **single-tenant, self-hosted** app: one Postgres
database holds exactly one person's financial data, and the only access
control is an optional instance-wide HTTP Basic Auth gate
(`AURUM_BASIC_AUTH_USER`/`AURUM_BASIC_AUTH_PASSWORD`, enforced by nginx via
`frontend/docker-entrypoint.d/20-basic-auth.sh`, with `LoginGate`/
`LoginScreen` on the frontend mirroring the same credentials so the browser's
native Basic Auth prompt never fires). No table has a concept of "owner" —
every row belongs to the one instance.

This project is now moving to a **multi-tenant model**: many users register
accounts on a shared, centrally hosted deployment, each with their own
private financial data. This is a prerequisite for the planned Android
client (a mobile app makes sense as "log into your account from your phone,"
not "point this app at whichever self-hosted server you happen to run").

This is one sub-project of a larger initiative (see conversation history):
backend multi-tenancy (this doc) → frontend web login/registration screens →
Android app → hosting/scaling infrastructure. Each gets its own design/plan
cycle. This doc covers **only the backend**.

Single-instance self-hosting is being fully replaced, not kept as a second
mode — confirmed with the project owner. The existing instance has no
production data worth migrating — confirmed with the project owner — so
there is no backfill/migration-of-existing-rows concern, only schema design
for a fresh start.

## Goals

- Multiple users can register and log in independently.
- Every user's financial data (accounts, transactions, categories, tags,
  budgets, goals, assets, crypto holdings, recurring payments, settings) is
  fully isolated from every other user's.
- A basic admin capability exists to list, disable, and delete user
  accounts.
- The crypto tracker continues to work for all users without hitting
  CoinGecko's rate limit.
- Existing test suite (`backend/tests`, run against real Postgres in CI)
  is extended to prove isolation, not just assert it by convention.

## Non-goals (explicitly deferred, do not build)

- Email verification on registration.
- Password reset / account recovery (no email channel exists for it yet;
  a lost password currently means a lost account — acceptable for this
  phase per the project owner).
- Invite-only / gated registration — registration is open to anyone.
- Postgres Row-Level Security. Isolation is enforced by the scoped-query
  layer described below, not by the database itself. Revisit only if a
  real isolation bug is found in production that this layer would not
  have caught.
- Per-user CoinGecko API keys. One shared backend-wide key remains; the
  rate-limit problem is solved by response caching (below), not by
  fan-out to per-user keys.
- Migrating any existing single-instance data — there is none to migrate.
- Preserving the single-instance self-hosted mode as a fallback/second
  deployment target.

## Data model changes

New table `users`:
| column | type | notes |
|---|---|---|
| id | int, PK | |
| email | str, unique, indexed | login identifier |
| password_hash | str | via `passlib` (bcrypt or argon2) |
| is_admin | bool, default false | |
| is_active | bool, default true | admin "disable account" flips this |
| created_at | timestamptz | |

New table `refresh_tokens`:
| column | type | notes |
|---|---|---|
| id | int, PK | |
| user_id | FK → users.id, cascade delete | |
| token_hash | str | SHA-256 of the token, never the raw token |
| expires_at | timestamptz | |
| revoked_at | timestamptz, nullable | set on logout or on rotation |

`user_id` (FK → `users.id`, `NOT NULL`, `ON DELETE CASCADE`) is added to
every existing domain table: `accounts`, `transactions`, `categories`,
`tags`, `budgets`, `goals`, `assets`, `asset_valuations`,
`crypto_holdings`, `crypto_transactions`, `recurring_payments`,
`app_settings`.

`app_settings` stops being the single-row-with-`id=1` singleton it is
today (see its existing docstring in `backend/app/models/settings.py`) and
becomes one row per user, created at registration time with the same
defaults it has now.

Alembic migrations add these columns as `NOT NULL` with no backfill step,
since there is no existing data to preserve.

## Auth flow

- `POST /api/auth/register` — `{email, password}` → creates `User` +
  that user's `AppSettings` row + their default category set (same list
  the instance-wide seed creates today, now created per-user instead of
  once per instance) → returns an access/refresh token pair.
- `POST /api/auth/login` — `{email, password}` → verifies password hash →
  returns a new access/refresh token pair.
- `POST /api/auth/refresh` — `{refresh_token}` → validates against
  `refresh_tokens` (must exist, match hash, not expired, not revoked) →
  issues a new access token **and rotates the refresh token** (old one
  marked `revoked_at`, a new one issued) so a leaked refresh token has a
  bounded window of use.
- `POST /api/auth/logout` — revokes the presented refresh token.

Both tokens are JWTs carrying `user_id`; access tokens are stateless
(15 min expiry, no DB check needed to validate); refresh tokens are
additionally checked against `refresh_tokens` so they're individually
revocable.

The existing instance-wide Basic Auth mechanism (env vars, nginx
`auth_basic`, `20-basic-auth.sh`) is removed entirely — it doesn't compose
with per-user accounts. `frontend/src/lib/auth.ts` and `LoginGate`/
`LoginScreen` are rewritten to hold a JWT pair instead of a Basic Auth
header, but the shape of the pattern carries over directly: the client
still attaches its own `Authorization` header on every request rather than
relying on any browser-native prompt, and a 401 still clears stored
credentials and falls back to the login screen — only the token type and
the refresh step are new. (This rewrite belongs to the frontend
sub-project, not this one; mentioned here only so the backend's token
shape is designed with that consumer in mind.)

## Authorization / data isolation (chosen approach)

Three approaches were considered:

1. **Explicit per-route filtering** — every route/service hand-writes
   `.where(Model.user_id == current_user.id)`. Simplest, but the
   correctness of every one of ~19 routers depends on nobody forgetting
   the filter, forever, including in every future PR.
2. **Postgres Row-Level Security** — the database itself refuses to
   return rows outside the caller's `user_id`, independent of application
   code. Genuinely stronger, but async SQLAlchemy needs a `SET LOCAL
   app.user_id` per transaction wired through the session/connection
   lifecycle, every migration must define matching policies, and it adds
   a debugging layer ("why did this query return nothing") the team has
   no prior experience operating. Rejected as disproportionate to current
   scale.
3. **Explicit filtering through one shared scoped-query layer (chosen)**
   — same DB-level shape as (1), but every service goes through one
   central helper instead of repeating `.where(...)` by hand. One place
   to get right instead of nineteen.

`app/api/deps.py` gains `get_current_user(token: str = Depends(...)) ->
User`, decoding the access JWT and loading the user (401 if invalid/
expired/inactive).

A new `app/services/scoped.py` provides the shared query helper — e.g. a
small function/class wrapping `select(Model).where(Model.user_id ==
user_id)` that every existing service (`accounts`, `transactions`,
`categories`, etc.) calls instead of building `select(Model)` directly.
Each of the ~19 existing routers is updated to take `current_user: User =
Depends(get_current_user)` and thread it through to its service calls.

## Admin

`User.is_admin` gates a new `get_current_admin` dependency (403 if
`is_admin` is false). New routes:

- `GET /api/admin/users` — list all users (email, created_at, is_active,
  is_admin — never password_hash).
- `PATCH /api/admin/users/{id}` — currently only supports toggling
  `is_active` (disable/re-enable a login).
- `DELETE /api/admin/users/{id}` — deletes the user; `ON DELETE CASCADE`
  on every domain table's `user_id` FK removes all their data with it.

No self-service "become admin" path exists — the first admin is granted
by a one-off manual DB update or a small `scripts/` helper run by whoever
operates the deployment, mirroring how `scripts/seed_mock_data.py` is
already invoked (`docker compose exec backend python -m scripts....`).

## Crypto price caching

The single shared `AURUM_COINGECKO_API_KEY` env var is kept as-is — this
sub-project does not change how the backend authenticates to CoinGecko.
What changes: a cached-price layer sits between users and CoinGecko —
prices for held symbols are fetched at most once per TTL window (e.g. 60s)
by a single background refresh, and all users' requests read that cache
instead of each triggering their own CoinGecko call. This keeps call
volume roughly constant as the user count grows, instead of scaling
linearly with it.

## Testing

`backend/tests` already runs against a real Postgres instance in CI (see
`.github/workflows/ci.yml`). This sub-project adds:

- Auth-flow tests: register, login (correct/incorrect password), refresh
  (valid/expired/revoked token), logout, and rotation (old refresh token
  rejected after a new one is issued from it).
- Isolation tests, one per domain router: a fixture creates two users
  (A, B) each with their own data; every list/get/update/delete endpoint
  is checked to (a) return only A's rows for A's token and (b) 404/403
  when A's token is used against B's resource id. This is the direct test
  for "somebody forgot the scoped-query helper somewhere."
- Admin tests: non-admin gets 403 on admin routes; admin can list/disable/
  delete; a disabled user's existing tokens stop working.

## Rollout / CI impact

No docker-compose topology change — still `db` + `backend` + `web`. The
`web` container's nginx config drops the Basic Auth entrypoint script
entirely. `.env.example` loses `AURUM_BASIC_AUTH_USER`/
`AURUM_BASIC_AUTH_PASSWORD` and gains whatever JWT signing secret the
implementation needs (e.g. `AURUM_JWT_SECRET`). `ci.yml`'s existing
`backend-tests` job needs no structural change — it already runs
`pytest -v` against a real Postgres service; it just now exercises more
tests.
