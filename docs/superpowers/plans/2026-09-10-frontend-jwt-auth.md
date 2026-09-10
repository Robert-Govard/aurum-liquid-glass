# Frontend JWT Login & Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the frontend's current "HTTP Basic Auth dressed up in
JavaScript" implementation with a real per-user JWT session, backed by the
backend's already-existing `/auth/register`, `/auth/login`, `/auth/refresh`,
`/auth/logout`, `/auth/me` endpoints — giving every user their own account
with their own login, instead of one shared instance-wide password.

**Design (confirmed with the user before writing this plan):** keep the
existing "gate above the router" architecture (`LoginGate` wraps `<App>`,
switching between an auth screen and the app — no react-router guards on
individual routes). Refresh token always in `localStorage` (no "remember
me" checkbox — this is standard JWT behavior, not something to opt into).
Access token in memory only, with automatic silent refresh-and-retry on a
401 in the shared API client. One combined login/register screen with a
mode toggle, replacing the old single-purpose `LoginScreen`. A new,
previously-nonexistent user menu (email + logout) in the `Topbar`, since
there is currently zero UI anywhere for "who am I / how do I sign out."

**Architecture:** `lib/auth.ts` is rewritten from the ground up — same
reactive-external-store shape as the file it replaces (`useSyncExternalStore`
+ a module-level state object + a `subscribe`/`notify` pair), but holding a
real access/refresh token pair and the current user's identity instead of
a Basic Auth header. `api/client.ts`'s single `request()` wrapper switches
from an `Authorization: Basic ...` header to `Authorization: Bearer ...`,
and gains the one piece of real complexity this plan introduces: on a 401,
try exactly one silent token refresh, retry the original request once with
the new token, and only give up (clearing the session) if that also fails.
Concurrent 401s (several API calls in flight when the access token expires
at once) share a single in-flight refresh attempt via a module-level
promise, so a page that fires several queries at once doesn't burn through
multiple refresh calls — each of which would otherwise try to consume the
same one-time-use refresh token and fail after the first.

**Tech Stack:** React 19, TypeScript, Vite, react-router-dom v7 (already a
dependency), Tailwind v4, `@tanstack/react-query` v5 — no new dependencies;
forms stay hand-rolled `useState` (no form library exists in this codebase
today, matching `AccountFormModal`'s and the old `LoginScreen`'s own style).

**Spec:** none — this is bounded work extending an existing flow
(`LoginGate`/`LoginScreen`/`auth.ts` already exist), confirmed with the
user via a short in-chat design rather than a full architectural spec.

## Global Constraints

- No new npm dependencies.
- The access token is NEVER written to any storage (`localStorage`,
  `sessionStorage`, or otherwise) — memory only, so it can't be read back
  by a persisted XSS payload and naturally disappears on tab close/reload.
- The refresh token is rotated by the backend on every successful use (see
  `services/auth_service.py`'s atomic `UPDATE ... WHERE revoked_at IS
  NULL`) — every successful refresh call MUST overwrite the stored refresh
  token with the new one, not just update the access token, or the next
  refresh attempt uses an already-consumed token and fails even though the
  session should still be alive.
- Concurrent 401s must not each independently call `/auth/refresh` — they
  share one in-flight attempt (see Architecture above).
- Every existing comment being touched gets updated to explain the new
  reality, never silently deleted (CLAUDE.md project rule) — several of
  this plan's own code blocks below explicitly carry forward and update
  the reasoning from the file they replace.
- All new UI is mobile-responsive from the start (CLAUDE.md project rule)
  — the existing `AuthScreen`'s mobile-first layout (`min-h-screen`,
  `px-4`, `Card` `w-full max-w-sm`) is preserved as-is; the new Topbar user
  menu hides the email text below the `sm` breakpoint, keeping only the
  logout icon, so it never crowds the mobile header.
- **No automated frontend test suite exists in this repo** (`package.json`
  has no test script, no vitest/jest, no `*.test.ts*` files anywhere) —
  confirmed before writing this plan. Verification in this plan means:
  `npm run build` (runs `tsc -b && vite build` — catches type errors and
  confirms the bundle compiles) after every task, plus each task's own
  written reasoning about why the logic is correct (mirroring how this
  project's backend plans verify a tricky concurrency fix by walking
  through the actual sequence of events, not just asserting it). A real
  browser-based smoke test of the login/register/logout flow happens once,
  manually, after all tasks are done — see the final task.

---

## Task 1: Rewrite `lib/auth.ts` and `api/client.ts` (no UI yet)

**Files:**
- Modify: `frontend/src/lib/auth.ts` (full rewrite)
- Modify: `frontend/src/api/client.ts` (full rewrite)

**Interfaces:**
- Produces: `getAccessToken(): string | null`, `getCurrentUser():
  CurrentUser | null`, `useAuthState(): { accessToken: string | null; user:
  CurrentUser | null }`, `login(email, password): Promise<AuthResult>`,
  `register(email, password): Promise<AuthResult>`, `logout(): Promise<void>`,
  `refreshAccessToken(): Promise<string | null>`, `bootstrap(): Promise<void>`,
  `clearSession(): void`. `AuthResult = "ok" | "invalid" | "email_taken" |
  "error" | "unreachable"`. Task 2 (`AuthScreen`, `LoginGate`) and Task 3
  (`Topbar`) both consume these.

- [ ] **Step 1: Write the new `lib/auth.ts`**

Replace the whole file:

```typescript
import { useSyncExternalStore } from "react";

/**
 * Client-side JWT session state — replaces the earlier HTTP-Basic-Auth-
 * in-JavaScript implementation this file used to hold, now that the
 * backend has real per-user accounts (see backend/app/api/routes/auth.py).
 *
 * Two tokens, two lifetimes, two storage tiers:
 *  - The access token (15 min) lives ONLY in memory (a module-level
 *    variable) — never written to any storage, so it can't be read back
 *    by an XSS payload that persists across page loads, and it naturally
 *    disappears on refresh/close.
 *  - The refresh token (30 days) is what actually keeps a session alive
 *    across reloads — stored in localStorage, the standard place for a
 *    long-lived JWT refresh token in a web app. There's no "remember me"
 *    checkbox because there's nothing to opt into: signing in always
 *    persists, the same way it does on basically every JWT-based site.
 * On every successful refresh the backend ROTATES the refresh token (see
 * services/auth_service.py's atomic UPDATE ... WHERE revoked_at IS NULL) —
 * the old one stops working the moment a new one is issued, so the stored
 * refresh token is overwritten on every use, not just the access token,
 * or the next refresh attempt would fail even though the session should
 * still be alive.
 */
const REFRESH_TOKEN_KEY = "aurum:refreshToken";
const USER_CACHE_KEY = "aurum:user";

export interface CurrentUser {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
}

interface AuthState {
  accessToken: string | null;
  user: CurrentUser | null;
}

interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

function readCachedUser(): CurrentUser | null {
  try {
    const raw = localStorage.getItem(USER_CACHE_KEY);
    return raw ? (JSON.parse(raw) as CurrentUser) : null;
  } catch {
    return null;
  }
}

function readRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

// The access token always starts null, even if a refresh token is stored
// from a previous session — LoginGate's bootstrap() call (see below) is
// what turns a stored refresh token back into a live access token + user
// on page load. The cached user is read eagerly so a returning user's
// email can render immediately once bootstrap succeeds, without an extra
// flash of "no user yet".
let state: AuthState = { accessToken: null, user: readCachedUser() };
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function setState(next: Partial<AuthState>): void {
  state = { ...state, ...next };
  try {
    if (state.user) localStorage.setItem(USER_CACHE_KEY, JSON.stringify(state.user));
    else localStorage.removeItem(USER_CACHE_KEY);
  } catch {
    // storage unavailable (private browsing, storage disabled) — the
    // session still works for this tab's life via the in-memory state, it
    // just won't survive a reload.
  }
  notify();
}

export function getAccessToken(): string | null {
  return state.accessToken;
}

export function getCurrentUser(): CurrentUser | null {
  return state.user;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthState(): AuthState {
  return useSyncExternalStore(subscribe, () => state);
}

function storeTokenPair(pair: TokenPair): void {
  try {
    localStorage.setItem(REFRESH_TOKEN_KEY, pair.refresh_token);
  } catch {
    // ignore — the session just won't survive a reload this time
  }
  setState({ accessToken: pair.access_token });
}

async function fetchCurrentUser(accessToken: string): Promise<CurrentUser> {
  const response = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${accessToken}` } });
  if (!response.ok) throw new Error("Failed to load current user");
  return (await response.json()) as CurrentUser;
}

export type AuthResult = "ok" | "invalid" | "email_taken" | "error" | "unreachable";

export async function login(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (response.status === 401) return "invalid";
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

export async function register(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (response.status === 409) return "email_taken";
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

/** Clears the whole session locally — called on an explicit logout, or
 * when a token refresh itself fails (invalid/expired/revoked refresh
 * token), so LoginGate falls back to the auth screen instead of every
 * subsequent request failing the same way forever. */
export function clearSession(): void {
  try {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_CACHE_KEY);
  } catch {
    // ignore — nothing to clean up if storage was never usable
  }
  setState({ accessToken: null, user: null });
}

export async function logout(): Promise<void> {
  const refreshToken = readRefreshToken();
  clearSession();
  if (!refreshToken) return;
  // Best-effort — the whole point of logging out is that the session
  // stops working locally regardless of whether the server-side revoke
  // call itself succeeds (e.g. the user is offline), so a failure here is
  // silently ignored rather than blocking the logout the user just asked for.
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    // ignore
  }
}

// Concurrent 401s (several API calls in flight at the moment the access
// token expires) must not each fire their own refresh call — the refresh
// token is single-use (rotated on every call, see the module docstring),
// so a second concurrent refresh would send the same token the first one
// already consumed and get rejected. Every caller within the same expiry
// window shares this one in-flight promise instead.
let refreshPromise: Promise<string | null> | null = null;

/** Exchanges the stored refresh token for a fresh pair, updating BOTH
 * stored tokens. Returns the new access token, or null if there was no
 * refresh token to use, or the refresh call itself failed for a reason
 * other than a network error (an invalid/expired/revoked refresh token),
 * in which case the session is cleared — the caller should treat a null
 * return as "the user is logged out now." A network-level failure (the
 * `catch` below) does NOT clear the session, since that's not evidence
 * the token itself is bad, just that this one attempt couldn't complete. */
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = readRefreshToken();
    if (!refreshToken) return null;
    try {
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        clearSession();
        return null;
      }
      const pair = (await response.json()) as TokenPair;
      storeTokenPair(pair);
      return pair.access_token;
    } catch {
      return null;
    }
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

/** Called once by LoginGate on mount. Turns a stored refresh token (from
 * a previous session, still present after a page reload) back into a live
 * access token + user, so a returning user doesn't see the auth screen
 * for even a moment. A missing or already-expired refresh token simply
 * leaves the session logged-out, same as if this were never called. */
export async function bootstrap(): Promise<void> {
  if (!readRefreshToken() || state.accessToken) return;
  const accessToken = await refreshAccessToken();
  if (!accessToken) return; // refreshAccessToken() already cleared the session if the token was genuinely invalid
  try {
    const user = await fetchCurrentUser(accessToken);
    setState({ user });
  } catch {
    // Access token came back fine but /auth/me itself failed (e.g. a
    // transient network hiccup) — leave the token in place; the cached
    // user from localStorage (if any) keeps the UI usable in the meantime.
  }
}
```

- [ ] **Step 2: Write the new `api/client.ts`**

Replace the whole file:

```typescript
import { clearSession, getAccessToken, refreshAccessToken } from "@/lib/auth";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function doFetch(path: string, init: RequestInit | undefined, accessToken: string | null): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    ...init,
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await doFetch(path, init, getAccessToken());

  if (response.status === 401) {
    // The access token is missing or expired — try exactly once to
    // refresh it and replay this same request before giving up.
    // Concurrent 401s from other in-flight requests share the same
    // refresh attempt (see lib/auth.ts's refreshPromise dedup), so a page
    // that fires several API calls at once doesn't burn through multiple
    // refresh attempts against a single-use refresh token.
    const newToken = await refreshAccessToken();
    if (newToken) {
      response = await doFetch(path, init, newToken);
    }
  }

  if (response.status === 401) {
    // Still unauthorized after the refresh-and-retry above — whether
    // because there was no refresh token to try, the refresh itself
    // failed (already cleared inside refreshAccessToken), or even the
    // retried request came back unauthorized with a fresh token, the
    // session is over. Clearing here too (harmless no-op if already
    // cleared) guarantees LoginGate falls back to the auth screen instead
    // of every subsequent request failing the same way forever.
    clearSession();
  }

  if (!response.ok) {
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      // body wasn't JSON — fall back to the raw text set above
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
```

- [ ] **Step 3: Verify the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no TypeScript errors. At this point `LoginGate.tsx`
and `LoginScreen.tsx` still import the OLD names (`checkCredentials`,
`useAuthHeader`, `buildBasicAuthHeader`, `setCredentials`) from `lib/auth.ts`,
which this step just removed — the build WILL fail on those two files'
imports. This is expected and is Task 2's job to fix, dispatched right
after this one. Confirm the only build errors are in `LoginGate.tsx`/
`LoginScreen.tsx` (missing-export errors naming the old functions), not
anywhere else — if `api/client.ts` or any other file fails to build,
investigate before concluding this task is done.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/auth.ts frontend/src/api/client.ts
git commit -m "Заменить Basic Auth на JWT-сессию в auth.ts и api-клиенте"
```

---

## Task 2: Rewrite the auth screen and `LoginGate`, add i18n copy

**Files:**
- Delete: `frontend/src/components/auth/LoginScreen.tsx`
- Create: `frontend/src/components/auth/AuthScreen.tsx`
- Modify: `frontend/src/components/auth/LoginGate.tsx`
- Modify: `frontend/src/lib/i18n.ts`

**Interfaces:**
- Consumes: `login`, `register`, `bootstrap`, `useAuthState`,
  `AuthResult` (Task 1).
- Produces: `AuthScreen` (default-exported-by-name component), used only
  by `LoginGate` in this same task.

- [ ] **Step 1: Add/update i18n keys**

Modify `frontend/src/lib/i18n.ts`. In the Russian (`ru`) block, replace:

```typescript
  "auth.subtitle": "Личные финансы",
  "auth.usernameLabel": "Логин",
  "auth.passwordLabel": "Пароль",
  "auth.rememberMe": "Запомнить меня на 30 дней",
  "auth.submitButton": "Войти",
  "auth.submitting": "Вход…",
  "auth.errorInvalidCredentials": "Неверный логин или пароль",
  "auth.errorUnreachable": "Не удалось подключиться к серверу. Проверьте соединение и попробуйте снова.",
```

with:

```typescript
  "auth.subtitle": "Личные финансы",
  "auth.emailLabel": "Email",
  "auth.passwordLabel": "Пароль",
  "auth.passwordHint": "Минимум 8 символов",
  "auth.submitButton": "Войти",
  "auth.submitting": "Вход…",
  "auth.registerButton": "Зарегистрироваться",
  "auth.registering": "Регистрация…",
  "auth.switchToRegister": "Нет аккаунта? Зарегистрироваться",
  "auth.switchToLogin": "Уже есть аккаунт? Войти",
  "auth.errorInvalidCredentials": "Неверный email или пароль",
  "auth.errorEmailTaken": "Этот email уже зарегистрирован",
  "auth.errorGeneric": "Что-то пошло не так. Попробуйте ещё раз.",
  "auth.errorUnreachable": "Не удалось подключиться к серверу. Проверьте соединение и попробуйте снова.",
  "topbar.logout": "Выйти",
```

In the English (`en`) block, replace:

```typescript
  "auth.subtitle": "Personal finance",
  "auth.usernameLabel": "Username",
  "auth.passwordLabel": "Password",
  "auth.rememberMe": "Remember me for 30 days",
  "auth.submitButton": "Sign in",
  "auth.submitting": "Signing in…",
  "auth.errorInvalidCredentials": "Incorrect username or password",
  "auth.errorUnreachable": "Couldn't reach the server. Check your connection and try again.",
```

with:

```typescript
  "auth.subtitle": "Personal finance",
  "auth.emailLabel": "Email",
  "auth.passwordLabel": "Password",
  "auth.passwordHint": "At least 8 characters",
  "auth.submitButton": "Sign in",
  "auth.submitting": "Signing in…",
  "auth.registerButton": "Create account",
  "auth.registering": "Creating account…",
  "auth.switchToRegister": "No account? Create one",
  "auth.switchToLogin": "Already have an account? Sign in",
  "auth.errorInvalidCredentials": "Incorrect email or password",
  "auth.errorEmailTaken": "This email is already registered",
  "auth.errorGeneric": "Something went wrong. Please try again.",
  "auth.errorUnreachable": "Couldn't reach the server. Check your connection and try again.",
  "topbar.logout": "Log out",
```

(`auth.usernameLabel`/`auth.rememberMe` are removed outright, not just
updated — they name concepts, a username field and a remember-me
checkbox, that no longer exist anywhere in the app after this plan. This
is a translation-dictionary cleanup, not a code-comment deletion, so
CLAUDE.md's comment-preservation rule doesn't apply here.)

- [ ] **Step 2: Create `AuthScreen.tsx`**

Create `frontend/src/components/auth/AuthScreen.tsx`:

```tsx
import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { login, register, type AuthResult } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Mode = "login" | "register";
type Status = "idle" | "submitting" | AuthResult;

const ERROR_KEYS: Partial<Record<Status, string>> = {
  invalid: "auth.errorInvalidCredentials",
  email_taken: "auth.errorEmailTaken",
  error: "auth.errorGeneric",
  unreachable: "auth.errorUnreachable",
};

/** Shown by LoginGate whenever there's no live session — collects an
 * email/password and either signs in or creates a new account (see
 * lib/auth.ts's login()/register()), which is what actually establishes
 * the session every subsequent request authenticates with. On success
 * this component doesn't navigate anywhere itself — LoginGate's
 * useAuthState() reactively swaps to rendering the app the moment
 * lib/auth.ts's session state changes, so this just stops being rendered. */
export function AuthScreen() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("submitting");
    const result = await (mode === "login" ? login(email, password) : register(email, password));
    setStatus(result);
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setStatus("idle");
  };

  const errorKey = ERROR_KEYS[status];

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
            <span className="text-xs text-text-muted">{t("auth.subtitle")}</span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            <div>
              <Label htmlFor="auth-email">{t("auth.emailLabel")}</Label>
              <Input
                id="auth-email"
                name="email"
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="auth-password">{t("auth.passwordLabel")}</Label>
              <Input
                id="auth-password"
                name="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {mode === "register" && <p className="mt-1 text-xs text-text-muted">{t("auth.passwordHint")}</p>}
            </div>

            {errorKey && <p className="text-sm text-danger">{t(errorKey as Parameters<typeof t>[0])}</p>}

            <Button type="submit" className="w-full" disabled={status === "submitting"}>
              {status === "submitting"
                ? t(mode === "login" ? "auth.submitting" : "auth.registering")
                : t(mode === "login" ? "auth.submitButton" : "auth.registerButton")}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => switchMode(mode === "login" ? "register" : "login")}
            className="text-xs text-text-secondary underline-offset-2 hover:underline"
          >
            {t(mode === "login" ? "auth.switchToRegister" : "auth.switchToLogin")}
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
```

Note on the `errorKey as Parameters<typeof t>[0]` cast: `ERROR_KEYS`'s
values are plain `string`, but `t()` expects the stricter `TranslationKey`
union type (see `lib/i18n.ts`). If this cast trips a lint rule or feels
too loose, an equally valid alternative is typing `ERROR_KEYS` directly as
`Partial<Record<Status, TranslationKey>>` (importing `TranslationKey` from
`lib/i18n.ts`) instead of casting at the call site — either is fine, pick
whichever this codebase's existing lint config prefers if it complains.

- [ ] **Step 3: Delete the old `LoginScreen.tsx`**

```bash
git rm frontend/src/components/auth/LoginScreen.tsx
```

- [ ] **Step 4: Rewrite `LoginGate.tsx`**

Replace the whole file:

```tsx
import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { bootstrap, useAuthState } from "@/lib/auth";

type Phase = "bootstrapping" | "ready";

/** Wraps the whole app. On mount, tries to turn a stored refresh token
 * (see lib/auth.ts) back into a live session — a fresh access token plus
 * the current user — before deciding what to render, so a page reload
 * doesn't flash the auth screen for an already-logged-in user. Once
 * bootstrapped, this is purely reactive: AuthScreen and the app swap
 * automatically whenever lib/auth.ts's session state changes (login,
 * register, logout, or a failed token refresh), no polling needed. */
export function LoginGate({ children }: { children: ReactNode }) {
  const { accessToken } = useAuthState();
  const [phase, setPhase] = useState<Phase>("bootstrapping");

  useEffect(() => {
    let cancelled = false;
    bootstrap().finally(() => {
      if (!cancelled) setPhase("ready");
    });
    return () => {
      cancelled = true;
    };
    // Deliberately runs once on mount only — later session changes are
    // handled by useAuthState() re-rendering this component directly, not
    // by re-running the bootstrap probe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (phase === "bootstrapping") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (!accessToken) {
    return <AuthScreen />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 5: Verify the build**

Run: `cd frontend && npm run build`
Expected: succeeds cleanly — no missing-export or missing-file errors.
Every reference to the old `LoginScreen`, `checkCredentials`,
`useAuthHeader`, `buildBasicAuthHeader`, `setCredentials` should be gone
from the whole `frontend/src` tree; confirm with
`grep -rn "checkCredentials\|useAuthHeader\|buildBasicAuthHeader\|setCredentials\|LoginScreen" frontend/src`
returning nothing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/auth/AuthScreen.tsx frontend/src/components/auth/LoginGate.tsx frontend/src/lib/i18n.ts
git commit -m "Добавить экран входа и регистрации на JWT, обновить LoginGate"
```

---

## Task 3: Add a user menu (email + logout) to the Topbar

**Files:**
- Modify: `frontend/src/components/layout/Topbar.tsx`

**Interfaces:**
- Consumes: `logout`, `useAuthState` (Task 1).

- [ ] **Step 1: Rewrite `Topbar.tsx`**

Replace the whole file:

```tsx
import { LogOut, Menu } from "lucide-react";
import { useLocation } from "react-router-dom";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { logout, useAuthState } from "@/lib/auth";

interface TopbarProps {
  onOpenMobileNav: () => void;
}

export function Topbar({ onOpenMobileNav }: TopbarProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { user } = useAuthState();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className={glassSurfaceClass("sticky top-0 z-30 flex items-center gap-3 border-b border-glass-border px-4 py-3.5 sm:px-6 lg:px-8")}>
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label={t("topbar.openMenu")}
        className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2 lg:hidden"
      >
        <Menu size={20} />
      </button>
      <h1 className="text-lg font-semibold text-text-primary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</h1>
      {user && (
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* Hidden below sm: the header is already tight on a phone
              screen with the hamburger button and page title, and the
              logout icon alone is enough to act on there — the email is a
              nice-to-have identity check, not something a mobile user
              needs visible at all times. */}
          <span className="hidden truncate text-xs text-text-muted sm:inline" title={user.email}>
            {user.email}
          </span>
          <button
            type="button"
            onClick={() => void logout()}
            aria-label={t("topbar.logout")}
            title={t("topbar.logout")}
            className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2"
          >
            <LogOut size={18} />
          </button>
        </div>
      )}
    </header>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: succeeds cleanly.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/Topbar.tsx
git commit -m "Добавить меню пользователя (email и выход) в Topbar"
```

---

## Task 4: Manual end-to-end verification (no automated test suite exists)

**Files:** none — this task verifies, it doesn't change code.

This project has no frontend test runner. This task is the closest
substitute: a real browser session against the actual running stack,
exercising the full register → reload → logout → login cycle, plus a
direct check of the token-refresh path this plan's whole design hinges on.

- [ ] **Step 1: Bring up the stack and open the app**

From the repo root: `docker compose up -d --build`, then open
`http://localhost:3000` (or whatever `AURUM_WEB_PORT` is set to) in a
real browser.

- [ ] **Step 2: Register a new account**

Confirm the auth screen shows an email/password form with a "no account?
create one" toggle (RU or EN depending on the browser's language
detection / whatever this app's language default is). Switch to register
mode, enter a real-looking email and an 8+ character password, submit.
Confirm: the screen switches to the app itself (dashboard) with no error,
and the Topbar now shows the email you registered with, plus a logout icon.

- [ ] **Step 3: Confirm the session survives a reload**

Reload the page. Confirm you land directly on the dashboard (not the auth
screen) — this is `bootstrap()` successfully exchanging the stored refresh
token for a fresh access token. Open the browser's dev tools → Application
→ Local Storage and confirm `aurum:refreshToken` is present and
`aurum:user` holds your registered email — and confirm there is NO access
token anywhere in `localStorage`/`sessionStorage` (it must only ever be
in memory, per this plan's core security property).

- [ ] **Step 4: Log out and log back in**

Click the logout icon. Confirm you're back on the auth screen, and that
`localStorage`'s `aurum:refreshToken`/`aurum:user` are gone. Switch to
login mode, enter the same email/password, submit. Confirm you're back on
the dashboard.

- [ ] **Step 5: Confirm a second, independent account is genuinely isolated**

Open a private/incognito window (a fresh, separate `localStorage`),
register a SECOND account with a different email, add an account/
transaction as that second user. Switch back to the first window/account
and confirm you do NOT see the second user's data anywhere (this exercises
the already-merged backend isolation from earlier plans in this series —
this step is about confirming the FRONTEND correctly keeps two real
browser sessions from bleeding into each other, e.g. no stale cached
React Query data from one account leaking into the other after a login
switch in the same tab — if you want to test that specific edge case, log
out of the first account in the SAME tab/window and log into the second
one there instead of using a separate window, and check the same thing).

- [ ] **Step 6: Confirm a wrong password is rejected cleanly**

Log out, try logging in with the right email and a wrong password.
Confirm the "incorrect email or password" error message appears (not a
generic error, not a silent failure) and the form remains usable for a
retry.

- [ ] **Step 7: Report the result**

Write up what was checked and what (if anything) didn't behave as
expected — do not report this task as complete without having actually
done Steps 1-6 in a real browser. If any step fails, fix the underlying
code (in a new commit, going back to the relevant earlier task's file) and
re-verify from the failing step onward.

---

## Plan Self-Review Notes

- **Placeholder scan:** every step contains complete, real code — no
  "similar to above," no elided logic. The one explicitly-flagged judgment
  call (the `ERROR_KEYS`/`t()` type cast in Task 2) names a concrete
  alternative rather than leaving a gap.
- **Type consistency:** `AuthResult`'s five variants (Task 1) are matched
  exhaustively by `ERROR_KEYS`'s four error-state keys plus the unhandled
  `"ok"`/`"idle"`/`"submitting"` states in `AuthScreen` (Task 2) — every
  `AuthResult` value that can actually reach `status` after a submit
  (`"ok"` never does, since success unmounts this component instead) has
  a corresponding message.
- **No test suite exists** — explicitly verified before writing this plan
  (`package.json`, full-tree search for test files), not assumed. Task 4
  is this plan's substitute for automated coverage.

---

## Next Plan

**Retire Basic Auth:** now that a real per-user JWT login gates the SPA
itself, `AURUM_BASIC_AUTH_USER`/`PASSWORD`, nginx's `auth_basic` directive,
and `frontend/docker-entrypoint.d/20-basic-auth.sh` can be safely removed
without leaving the app with no login prompt at all — closing out the
multi-tenant series' originally-deferred Basic Auth retirement step. After
that, the originally-requested Android (Capacitor) app becomes unblocked.
