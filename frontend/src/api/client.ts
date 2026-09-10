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
