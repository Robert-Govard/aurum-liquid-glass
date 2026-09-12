import { useSyncExternalStore } from "react";
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

/**
 * Where a native (Android/iOS) build's backend actually lives.
 *
 * Moneta is self-hosted — every installer runs their own backend, there is
 * no canonical hosted URL this app could ship with. On the web this is
 * moot: the app is always served BY that same backend's own nginx, which
 * proxies /api/* same-origin, so a plain relative path already works and
 * always has. A native build has no such same-origin proxy — it needs an
 * absolute URL, collected once via ServerSetupScreen and persisted here.
 *
 * `Capacitor.isNativePlatform()` is the single switch between these two
 * worlds everywhere in this codebase that talks to the network — false
 * in a normal browser tab (including this same code running inside the
 * Vite dev server or a Docker-Compose-served build), true only inside the
 * actual native WebView shell.
 */
const SERVER_URL_KEY = "aurum:serverUrl";

/** Baked in only when this specific build was made for one known server
 * (see .github/workflows/ci.yml's android-build job, which sets this as a
 * build-time env var) — the generic, publicly-buildable app has no
 * default and always shows ServerSetupScreen empty on first launch, per
 * this file's own module-level comment above. Trimmed/de-slashed the same
 * way setServerUrl() normalizes a user-entered address. */
export const DEFAULT_SERVER_URL: string =
  (import.meta.env.VITE_DEFAULT_SERVER_URL as string | undefined)?.trim().replace(/\/+$/, "") ?? "";

interface ServerState {
  ready: boolean;
  serverUrl: string | null;
}

let state: ServerState = { ready: false, serverUrl: null };
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function setState(next: Partial<ServerState>): void {
  state = { ...state, ...next };
  notify();
}

export function isNative(): boolean {
  return Capacitor.isNativePlatform();
}

async function isServerReachable(origin: string): Promise<boolean> {
  try {
    const response = await fetch(`${origin}/api/health`);
    return response.ok;
  } catch {
    return false;
  }
}

/** Called once by ServerGate on mount. On the web this just marks state
 * ready immediately (there's nothing to load) — on native, it loads
 * whatever server URL was saved on a previous launch, if any. On a fresh
 * native install with nothing saved yet, tries DEFAULT_SERVER_URL once
 * (if this build has one) before falling back to ServerSetupScreen — a
 * build made for one specific server shouldn't make its own user type an
 * address they didn't choose. */
export async function bootstrapServerUrl(): Promise<void> {
  if (!isNative()) {
    setState({ ready: true });
    return;
  }
  const { value } = await Preferences.get({ key: SERVER_URL_KEY });
  if (value) {
    setState({ ready: true, serverUrl: value });
    return;
  }
  if (DEFAULT_SERVER_URL && (await isServerReachable(DEFAULT_SERVER_URL))) {
    await setServerUrl(DEFAULT_SERVER_URL);
    setState({ ready: true });
    return;
  }
  setState({ ready: true, serverUrl: null });
}

export async function setServerUrl(url: string): Promise<void> {
  // Strip any trailing slash(es) so getApiBase() below never produces a
  // doubled "//api" when it appends "/api" itself.
  const normalized = url.trim().replace(/\/+$/, "");
  await Preferences.set({ key: SERVER_URL_KEY, value: normalized });
  setState({ serverUrl: normalized });
}

/** Used by the Settings page's "change server" option — clears the saved
 * address so ServerGate falls back to ServerSetupScreen again. */
export async function clearServerUrl(): Promise<void> {
  await Preferences.remove({ key: SERVER_URL_KEY });
  setState({ serverUrl: null });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useServerState(): ServerState {
  return useSyncExternalStore(subscribe, () => state);
}

/** The prefix every API call in this app should use. A relative "/api" on
 * the web (unchanged from before this plan); the configured server's
 * absolute origin + "/api" on native, once one has been set. If this is
 * somehow called on native before a server URL is configured, it falls
 * back to the same relative form — that request will simply fail (there's
 * no same-origin backend to hit), which can only happen if some code path
 * calls the API before ServerGate has finished gating the app, a bug
 * worth surfacing loudly rather than masking. */
export function getApiBase(): string {
  return isNative() && state.serverUrl ? `${state.serverUrl}/api` : "/api";
}
