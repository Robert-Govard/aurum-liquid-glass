# Admin User Dashboard Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking a user in the admin panel's list opens a popup showing that user's dashboard (the same 4 stat cards as the real Dashboard page, with a month/year switcher) — a read-only "view as" window into their monthly activity.

**Architecture:** The backend's `dashboard_service.get_dashboard_summary(session, year, month, user_id)` is already parameterized by `user_id` (not implicitly "the current user") — this task is almost pure reuse: one new admin-gated route that validates the target user exists, then calls that same function. The frontend adds one new modal component (`Dialog` + reused `StatCard`/`MonthSelector`/`YearSelector`), wired to a click on each row in the already-existing `AdminUserList`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend, pytest via `httpx.AsyncClient`), React 19 + React Query + Tailwind v4 (frontend, no test framework — `npm run build` only).

**Spec:** `docs/superpowers/specs/2026-09-11-admin-user-dashboard-design.md`

## Global Constraints

- One new backend endpoint, zero new business logic — pure reuse of `get_dashboard_summary`. No new Pydantic schema (reuses the existing `DashboardSummary`).
- The popup's year switcher range comes from the target user's `created_at` (already present on `AdminUser`, from the year of registration through the current year) — computed client-side, no new "years" endpoint.
- Every amount in the popup is formatted in the TARGET user's currency (`AdminUser.currency`, already on the type from the earlier admin-panel currency fix), never the viewing admin's — same bug class already fixed once for the admin list's net-worth column.
- No new i18n keys — the popup reuses the existing `dashboard.*` keys (same ones the real Dashboard page uses) and the existing `admin.loadError` key.
- The modal component must stay mounted at all times in `AdminPage` (never conditionally rendered based on whether a user is selected) so `Dialog`'s own close-transition animation (a `setTimeout`-delayed unmount internal to `Dialog`) gets a chance to run — if the parent removed the whole modal component the instant the selected user goes back to `null`, `Dialog` itself would be unmounted immediately and never get to play its fade-out.
- No visual/device verification is possible in this environment — every task's testing section says so explicitly.

---

### Task 1: Backend — `GET /api/admin/users/{user_id}/dashboard-summary`

**Files:**
- Modify: `backend/app/api/routes/admin.py`
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: `dashboard_service.get_dashboard_summary(session, year, month, user_id) -> DashboardSummary` (pre-existing, unchanged), `app.schemas.dashboard.DashboardSummary` (pre-existing, unchanged), `app.models.user.User` (pre-existing).
- Produces: `GET /api/admin/users/{user_id}/dashboard-summary?year=&month=` — admin-gated (same router-level `get_current_admin` dependency as the rest of `/admin/*`), 404 if `user_id` doesn't exist, otherwise returns `DashboardSummary` for that user — consumed by Task 2's frontend `fetchAdminUserDashboard`.

- [ ] **Step 1: Add the new route**

In `backend/app/api/routes/admin.py`, replace the full file contents with:

```python
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_session
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.schemas.user import AdminUserRead, UserRead, UserUpdate
from app.services.dashboard_service import get_dashboard_summary
from app.services.user_service import delete_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[AdminUserRead])
async def list_users_route(session: AsyncSession = Depends(get_session)) -> list[AdminUserRead]:
    return await list_users(session)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_route(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> User:
    return await update_user(session, user_id, payload, current_admin.id)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_route(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_admin: User = Depends(get_current_admin),
) -> None:
    await delete_user(session, user_id, current_admin.id)


@router.get("/users/{user_id}/dashboard-summary", response_model=DashboardSummary)
async def user_dashboard_summary_route(
    user_id: int,
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await get_dashboard_summary(session, year, month, user_id)
```

(The new route doesn't need its own `current_admin: User = Depends(get_current_admin)` parameter — unlike `update_user_route`/`delete_user_route`, it doesn't need the ACTING admin's id for anything, only the router-level dependency's 403 gate, which already applies to every route in this file.)

- [ ] **Step 2: Run the existing test suite**

Run: `cd backend && python -m pytest -q`
Expected: all pass (this only adds a route; nothing existing changed behavior).

- [ ] **Step 3: Add new tests to `test_admin.py`**

Add `from decimal import Decimal` to the top of `backend/tests/test_admin.py` if not already imported (it was added in the earlier admin-panel plan's Task 2 — check first, don't duplicate), then add:

```python
async def test_non_admin_gets_403_on_dashboard_summary(client):
    tokens = await _register(client, "plaindash@example.com")
    resp = await client.get("/admin/users/1/dashboard-summary", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 403


async def test_admin_dashboard_summary_returns_404_for_missing_user(client, test_sessionmaker):
    admin_tokens = await _register(client, "dashadmin404@example.com")
    await _make_admin(test_sessionmaker, "dashadmin404@example.com")
    resp = await client.get("/admin/users/999999/dashboard-summary", headers=_auth(admin_tokens["access_token"]))
    assert resp.status_code == 404


async def test_admin_can_view_another_users_dashboard_summary(client, test_sessionmaker):
    admin_tokens = await _register(client, "dashadmin@example.com")
    await _make_admin(test_sessionmaker, "dashadmin@example.com")

    target_tokens = await _register(client, "dashtarget@example.com")
    target_account = (
        await client.post(
            "/accounts",
            json={"name": "Dash Wallet", "type": "checking", "currency": "USD"},
            headers=_auth(target_tokens["access_token"]),
        )
    ).json()
    target_categories = (await client.get("/categories", headers=_auth(target_tokens["access_token"]))).json()
    salary_id = next(c["id"] for c in target_categories if c["name"] == "Salary")
    await client.post(
        "/transactions",
        json={
            "account_id": target_account["id"],
            "type": "income",
            "amount": "777.00",
            "description": "salary",
            "date": "2026-01-15",
            "category_id": salary_id,
        },
        headers=_auth(target_tokens["access_token"]),
    )

    users = (await client.get("/admin/users", headers=_auth(admin_tokens["access_token"]))).json()
    target_id = next(u["id"] for u in users if u["email"] == "dashtarget@example.com")
    admin_id = next(u["id"] for u in users if u["email"] == "dashadmin@example.com")

    resp = await client.get(
        f"/admin/users/{target_id}/dashboard-summary",
        params={"year": 2026, "month": 1},
        headers=_auth(admin_tokens["access_token"]),
    )
    assert resp.status_code == 200
    assert Decimal(str(resp.json()["real_income"])) == Decimal("777.00")

    # The viewing admin's own (empty) dashboard must not leak the target's
    # income — this is the cross-user isolation check that matters here.
    admin_own_resp = await client.get(
        f"/admin/users/{admin_id}/dashboard-summary",
        params={"year": 2026, "month": 1},
        headers=_auth(admin_tokens["access_token"]),
    )
    assert Decimal(str(admin_own_resp.json()["real_income"])) == Decimal("0")
```

- [ ] **Step 4: Run the new tests**

Run: `cd backend && python -m pytest -q -k dashboard_summary`
Expected: 3 PASS.

- [ ] **Step 5: Run the full suite once more**

Run: `cd backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/api/routes/admin.py tests/test_admin.py
git commit -m "Добавить эндпоинт дашборда пользователя для админки"
```

---

### Task 2: Frontend — dashboard popup

**Files:**
- Modify: `frontend/src/api/admin.ts`
- Modify: `frontend/src/hooks/useAdmin.ts`
- Create: `frontend/src/components/admin/AdminUserDashboardModal.tsx`
- Modify: `frontend/src/components/admin/AdminUserList.tsx`
- Modify: `frontend/src/pages/AdminPage.tsx`

**Interfaces:**
- Consumes: `DashboardSummary` type (from `@/types`, pre-existing — fields `real_income, spent, net, transferred_out, spending_by_category`), `AdminUser` type (pre-existing, has `id, email, created_at, currency`), `StatCard` (from `@/components/dashboard/StatCard`, props `label/value/caption/tone`), `MonthSelector` (props `month: number, onChange: (month:number)=>void`), `YearSelector` (props `years: number[], year: number, onChange: (year:number)=>void`), `Dialog` (props `open/onClose/title/children`), `formatCurrency`/`formatSignedCurrency` (both `(amount: number|string, currency?: string) => string`).
- Produces: `fetchAdminUserDashboard(userId, year, month)` (from `@/api/admin`), `useAdminUserDashboard(userId: number | null, year, month)` (from `@/hooks/useAdmin`), `AdminUserDashboardModal` component — consumed by `AdminPage.tsx` in this same task.

- [ ] **Step 1: Add the API function**

In `frontend/src/api/admin.ts`, currently:

```ts
import { api } from "@/api/client";
import type { AdminUser } from "@/types";

export function fetchAdminUsers() {
  return api.get<AdminUser[]>("/admin/users");
}

export function updateAdminUser(id: number, input: { is_active: boolean }) {
  return api.patch<AdminUser>(`/admin/users/${id}`, input);
}

export function deleteAdminUser(id: number) {
  return api.delete<void>(`/admin/users/${id}`);
}
```

Change to:

```ts
import { api } from "@/api/client";
import type { AdminUser, DashboardSummary } from "@/types";

export function fetchAdminUsers() {
  return api.get<AdminUser[]>("/admin/users");
}

export function updateAdminUser(id: number, input: { is_active: boolean }) {
  return api.patch<AdminUser>(`/admin/users/${id}`, input);
}

export function deleteAdminUser(id: number) {
  return api.delete<void>(`/admin/users/${id}`);
}

export function fetchAdminUserDashboard(userId: number, year: number, month: number) {
  return api.get<DashboardSummary>(`/admin/users/${userId}/dashboard-summary?year=${year}&month=${month}`);
}
```

- [ ] **Step 2: Add the hook**

In `frontend/src/hooks/useAdmin.ts`, currently:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdminUser, fetchAdminUsers, updateAdminUser } from "@/api/admin";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
}
```

Change the import and add a new hook right after `useAdminUsers`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdminUser, fetchAdminUserDashboard, fetchAdminUsers, updateAdminUser } from "@/api/admin";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
}

export function useAdminUserDashboard(userId: number | null, year: number, month: number) {
  return useQuery({
    queryKey: ["admin-user-dashboard", userId, year, month],
    queryFn: () => fetchAdminUserDashboard(userId as number, year, month),
    // Same conditional-query pattern already used in hooks/useCrypto.ts and
    // hooks/useReports.ts — don't fire a request with a nonsense id before
    // any user has been selected in the admin list.
    enabled: userId !== null,
  });
}
```

(`useUpdateAdminUser`/`useDeleteAdminUser` further down in the file are unchanged — leave them exactly as they are.)

- [ ] **Step 3: Create the modal component**

Create `frontend/src/components/admin/AdminUserDashboardModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { useAdminUserDashboard } from "@/hooks/useAdmin";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

interface AdminUserDashboardModalProps {
  user: AdminUser | null;
  onClose: () => void;
}

/** Share of income left over after spending — same formula as
 * DashboardPage's own savingsRate(); duplicated rather than imported
 * since DashboardPage doesn't export it and it's a 2-line pure function. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

/** Read-only dashboard popup for one user, opened from AdminUserList.
 * Always mounted in AdminPage (never conditionally rendered based on
 * whether a user is selected) — Dialog's own close animation keeps ITSELF
 * mounted for a short timeout after `open` goes false, but that only
 * works if this wrapper component doesn't get removed from the tree
 * first. */
export function AdminUserDashboardModal({ user, onClose }: AdminUserDashboardModalProps) {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  // Keeps showing the last-viewed user's data while Dialog's close
  // animation plays (during which `user` has already gone back to null).
  const [displayUser, setDisplayUser] = useState<AdminUser | null>(user);
  useEffect(() => {
    if (user) setDisplayUser(user);
  }, [user]);

  const registrationYear = displayUser ? new Date(displayUser.created_at).getFullYear() : now.getFullYear();
  const years: number[] = [];
  for (let y = now.getFullYear(); y >= registrationYear; y--) years.push(y);

  const { data, isLoading, isError } = useAdminUserDashboard(displayUser?.id ?? null, year, month);
  const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;
  const currency = displayUser?.currency;

  return (
    <Dialog open={user !== null} onClose={onClose} title={displayUser?.email ?? ""}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <MonthSelector month={month} onChange={setMonth} />
          </div>
          <YearSelector years={years} year={year} onChange={setYear} />
        </div>

        {isError ? (
          <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {t("admin.loadError")}
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label={t("dashboard.statRealIncomeLabel")}
              value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0, currency)}
              caption={t("dashboard.statRealIncomeCaption")}
              tone="success"
            />
            <StatCard
              label={t("dashboard.statSpentLabel")}
              value={isLoading ? "…" : formatCurrency(data?.spent ?? 0, currency)}
              caption={t("dashboard.statSpentCaption")}
              tone="danger"
            />
            <StatCard
              label={t("dashboard.statNetLabel")}
              value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0, currency)}
              caption={t("dashboard.statNetCaption")}
              tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
            />
            <StatCard
              label={t("dashboard.statSavingsRateLabel")}
              value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
              caption={t("dashboard.statSavingsRateCaption")}
              tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
            />
          </div>
        )}
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 4: Wire a click on each row in `AdminUserList`**

In `frontend/src/components/admin/AdminUserList.tsx`, the props interface currently is:

```tsx
interface AdminUserListProps {
  items: AdminUser[];
  currentUserId: number | undefined;
  onToggleActive: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
}
```

Change to:

```tsx
interface AdminUserListProps {
  items: AdminUser[];
  currentUserId: number | undefined;
  onView: (user: AdminUser) => void;
  onToggleActive: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
}
```

The component signature currently is:

```tsx
export function AdminUserList({ items, currentUserId, onToggleActive, onDelete }: AdminUserListProps) {
```

Change to:

```tsx
export function AdminUserList({ items, currentUserId, onView, onToggleActive, onDelete }: AdminUserListProps) {
```

The row's info block currently is (the `<span className="min-w-0 flex-1">...</span>` wrapping email/badges/dates/stats):

```tsx
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-text-primary">
                <span className="min-w-0 truncate">{user.email}</span>
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {!user.is_active && (
                  <span className="shrink-0 rounded bg-danger/10 px-1 py-0.5 text-[10px] leading-none text-danger">
                    {t("admin.disabledBadge")}
                  </span>
                )}
              </span>
              <span className="block text-xs text-text-muted">
                {t("admin.registeredOn", { date: formatFullDate(user.created_at) })}
                {" · "}
                {user.last_login_at
                  ? t("admin.lastLoginOn", { date: formatFullDate(user.last_login_at) })
                  : t("admin.neverLoggedIn")}
              </span>
              <span className="block text-xs text-text-muted">
                {user.accounts_count} {accountsCountLabel(user.accounts_count, language)}
                {", "}
                {user.transactions_count} {transactionsCountLabel(user.transactions_count, language)}
                {" · "}
                {t("admin.netWorthLabel", { amount: formatCurrency(user.net_worth, user.currency) })}
              </span>
            </span>
```

Change ONLY the outer wrapping tag from `<span className="min-w-0 flex-1">` to a clickable button (everything inside stays byte-for-byte identical — it's still just `<span>`s, not nested buttons, so this is a valid, non-nested interactive element):

```tsx
            <button type="button" onClick={() => onView(user)} className="min-w-0 flex-1 text-left">
              <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-text-primary">
                <span className="min-w-0 truncate">{user.email}</span>
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {!user.is_active && (
                  <span className="shrink-0 rounded bg-danger/10 px-1 py-0.5 text-[10px] leading-none text-danger">
                    {t("admin.disabledBadge")}
                  </span>
                )}
              </span>
              <span className="block text-xs text-text-muted">
                {t("admin.registeredOn", { date: formatFullDate(user.created_at) })}
                {" · "}
                {user.last_login_at
                  ? t("admin.lastLoginOn", { date: formatFullDate(user.last_login_at) })
                  : t("admin.neverLoggedIn")}
              </span>
              <span className="block text-xs text-text-muted">
                {user.accounts_count} {accountsCountLabel(user.accounts_count, language)}
                {", "}
                {user.transactions_count} {transactionsCountLabel(user.transactions_count, language)}
                {" · "}
                {t("admin.netWorthLabel", { amount: formatCurrency(user.net_worth, user.currency) })}
              </span>
            </button>
```

(This click target is available on every row, including the viewer's own — viewing your own dashboard via the popup is harmless and redundant with the real Dashboard page, not a security concern; the self-lockout protection that hides the `Switch`/delete button on the own row is unrelated and untouched.)

- [ ] **Step 5: Wire the modal into `AdminPage`**

Replace the full contents of `frontend/src/pages/AdminPage.tsx` with:

```tsx
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { AdminUserDashboardModal } from "@/components/admin/AdminUserDashboardModal";
import { AdminUserList } from "@/components/admin/AdminUserList";
import { useAdminUsers, useDeleteAdminUser, useUpdateAdminUser } from "@/hooks/useAdmin";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

export function AdminPage() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuthState();
  const { data: users, isLoading, isError } = useAdminUsers();
  const updateUser = useUpdateAdminUser();
  const deleteUser = useDeleteAdminUser();
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  function handleToggleActive(user: AdminUser) {
    updateUser.mutate({ id: user.id, isActive: !user.is_active });
  }

  function handleDelete(user: AdminUser) {
    if (window.confirm(t("admin.confirmDelete", { email: user.email }))) {
      deleteUser.mutate(user.id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.admin")}</CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
              {t("admin.loadError")}
            </p>
          ) : isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AdminUserList
              items={users ?? []}
              currentUserId={currentUser?.id}
              onView={setSelectedUser}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>
      <AdminUserDashboardModal user={selectedUser} onClose={() => setSelectedUser(null)} />
    </div>
  );
}
```

- [ ] **Step 6: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/api/admin.ts src/hooks/useAdmin.ts src/components/admin/AdminUserDashboardModal.tsx src/components/admin/AdminUserList.tsx src/pages/AdminPage.tsx
git commit -m "Добавить попап с дашбордом пользователя в админ-панель"
```

---

## Self-Review Notes

- **Spec coverage:** new endpoint reusing `get_dashboard_summary` → Task 1. Modal with 4 stat cards + month/year switcher, year range from `created_at`, target-user currency, no new i18n → Task 2. The three explicitly-out-of-scope items (recent transactions, category breakdown donut, any editing from the popup) are correctly absent from both tasks.
- **Placeholder scan:** every step has literal, complete code.
- **Type consistency:** `useAdminUserDashboard(userId: number | null, ...)` (Task 2, Step 2) matches how it's called in `AdminUserDashboardModal` (Step 3: `useAdminUserDashboard(displayUser?.id ?? null, year, month)`) — `number | null` on both sides, not `number | undefined`. `fetchAdminUserDashboard(userId: number, year, month)` (Step 1) matches the hook's `queryFn: () => fetchAdminUserDashboard(userId as number, year, month)` cast (safe because `enabled: userId !== null` guarantees the query never actually runs with a null `userId`). `AdminUserListProps.onView` (Step 4) matches `onView={setSelectedUser}` in `AdminPage` (Step 5) — both `(user: AdminUser) => void`-shaped.
- **No task leaves the build/test suite broken:** Task 1 ends with a full `pytest` run; Task 2 ends with `npm run build`.
