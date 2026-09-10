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
