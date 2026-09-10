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
      if (response.status === 401) {
        // Retried with a genuinely fresh token and still unauthorized —
        // a real "not who you think you are" case, not a network hiccup.
        // refreshAccessToken() only handles ITS OWN failure modes; this
        // is the one 401 case only this function can see.
        clearSession();
      }
    }
    // newToken === null means refreshAccessToken() already made the
    // right call — cleared the session for an invalid/expired refresh
    // token, or deliberately left it alone for a network failure. Don't
    // second-guess that decision here: calling clearSession() again on a
    // plain network hiccup would violate auth.ts's own guarantee that a
    // transient network failure never logs the user out.
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
