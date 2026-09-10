# Android App via Capacitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Aurum as an installable Android app — a Capacitor wrapper
around the existing React web app, now that real per-user JWT login and
full multi-tenant data isolation make a shared backend safe to talk to
from a native client. This is the original request that started this
whole session, unblocked now that the auth/isolation work behind it is
done.

**Design (confirmed with the user before writing this plan):** Aurum
stays self-hosted (README's own framing — each installer runs their own
backend, there is no canonical hosted instance), so the Android app can't
ship with a backend URL baked in. On first launch it shows a "Server URL"
setup screen (same pattern Nextcloud/Home Assistant use), verifies the
address actually reaches a real Aurum backend before saving it, and
persists it via Capacitor's `Preferences` plugin. This build environment
has no Android SDK/JDK/Gradle installed, so no task in this plan can
locally compile or run the actual `.apk` — a new CI job builds a debug
APK on every push and uploads it as a downloadable artifact, which is how
this plan's work actually gets verified end-to-end (by the user, on a
real device, after each merge).

**Architecture:** `@capacitor/core` + `@capacitor/android` wrap the
existing Vite build output (`dist/`) in a native WebView shell — no
change to how the web app itself is built or deployed via Docker Compose.
`Capacitor.isNativePlatform()` is the single switch that separates native
behavior from web behavior everywhere it matters: on the web, the app
behaves EXACTLY as it does today (relative `/api` calls through nginx's
proxy, no server-setup screen ever shown); only on a native build does a
configured server URL get prepended to every API call, and only on native
does `ServerGate` ever render `ServerSetupScreen` instead of passing
through immediately. `lib/serverUrl.ts` is a new module built to the
exact same reactive-external-store shape `lib/auth.ts` already
established (module-level state object, `useSyncExternalStore`,
async `bootstrap`-style initialization) — not a new pattern, an extension
of the one already in this codebase.

**Tech Stack:** Capacitor 7 (`@capacitor/core`, `@capacitor/cli`,
`@capacitor/android`, `@capacitor/preferences`) — the only new
dependencies this plan adds. GitHub Actions gains one new job using
`android-actions/setup-android` (installs Android SDK components) and
`actions/setup-java` (JDK 17, what Capacitor 7's Gradle setup expects).

**Spec:** none — confirmed via a short in-chat design exchange (two
targeted questions on the two genuinely open decisions: server-URL UX,
and whether to add CI APK builds) rather than a full architectural spec
document, given how much of the surrounding design (multi-tenant backend,
JWT auth, self-hosted framing) was already locked in by prior,
already-merged plans this one directly builds on.

## Global Constraints

- The web app's behavior must be BYTE-IDENTICAL to before this plan when
  NOT running under Capacitor — every task that touches a shared file
  (`api/client.ts`, `lib/auth.ts`, `api/backup.ts`, `main.tsx`) must
  preserve the exact existing relative-`/api` behavior for a normal
  browser/Docker-Compose deployment. `Capacitor.isNativePlatform()`
  returns `false` in that context (Capacitor's own documented behavior
  when the app isn't running inside a native shell), which is what makes
  this safe.
- No local Android/Gradle build is possible in this environment — every
  task's own verification is `npm run build` (TypeScript/Vite, works
  exactly as before) plus reasoning about the native-specific code paths,
  same limitation and same substitute-verification approach the
  immediately preceding frontend-JWT-auth plan used. The actual native
  build is verified by CI (Task 5) and, ultimately, by the user installing
  the resulting APK on a real device.
- `frontend/android/` (the native project Capacitor generates) is a large
  tree of generated Gradle/Android boilerplate — commit it as Capacitor
  generates it (this is the standard, documented way to use Capacitor;
  unlike `node_modules`, the native platform folder IS meant to be
  version-controlled since it holds project-specific native config
  Capacitor doesn't regenerate from scratch on every `sync`).
- No new native features beyond what wrapping the existing (already
  mobile-responsive) web app in a WebView provides for free — no
  biometric lock, no push notifications, no deep links. Explicitly
  deferred, not overlooked.
- Every new user-facing string goes through `lib/i18n.ts`'s existing
  `ru`/`en` pattern, matching this whole codebase's established i18n
  convention.

---

## Task 1: Add Capacitor and scaffold the Android native project

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/capacitor.config.ts`
- Create: `frontend/android/` (generated by Capacitor's own CLI — not
  hand-written)

**Interfaces:** none — this task adds tooling only, no application code
changes.

- [ ] **Step 1: Install Capacitor**

From `frontend/`:

```bash
npm install @capacitor/core @capacitor/android @capacitor/preferences
npm install --save-dev @capacitor/cli
```

- [ ] **Step 2: Create `capacitor.config.ts`**

Create `frontend/capacitor.config.ts`:

```typescript
import type { CapacitorConfig } from "@capacitor/cli";

// appId follows Android's reverse-domain convention — change this before
// a real Play Store submission if a different domain is ever registered
// for this project; it only needs to be globally unique and stable once
// real users have installed a build under it (changing it later is
// effectively a new app from Android's point of view).
const config: CapacitorConfig = {
  appId: "com.aurum.app",
  appName: "Aurum",
  webDir: "dist",
};

export default config;
```

- [ ] **Step 3: Build the web app once, then scaffold Android**

Capacitor's `add` command needs `webDir` (`dist/`) to already exist:

```bash
npm run build
npx cap add android
```

This generates the whole `frontend/android/` native project (Gradle
wrapper, `AndroidManifest.xml`, module structure, etc.) — do not hand-edit
anything Capacitor just generated beyond what later tasks in this plan
explicitly call for.

- [ ] **Step 4: Add a sync script**

Modify `frontend/package.json`'s `"scripts"` block — add:

```json
    "cap:sync": "vite build && npx cap sync android",
```

(Placed alongside the existing `dev`/`build`/`preview` scripts — read the
current file to match its exact formatting/ordering conventions rather
than guessing. This is the command a developer runs after any web change
to copy the new build into the native project and refresh Capacitor's
native dependency manifest — Task 5's CI job runs the equivalent commands
directly, not via this script, but it's still useful for local
development on a machine that DOES have Android tooling.)

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run build`
Expected: succeeds exactly as before — this task adds a native project
alongside the web app, it doesn't change how the web app itself builds.
Confirm `frontend/android/` now exists with a `build.gradle`, `app/`
subdirectory, and `gradlew` script (Capacitor's standard scaffold) —
this is the one thing in this task that CAN'T be build-verified here
(no local Gradle), so confirm its presence and basic shape by listing the
directory instead.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/capacitor.config.ts frontend/android/
git commit -m "Добавить Capacitor и нативный Android-проект"
```

---

## Task 2: Dynamic API base URL for native builds

**Files:**
- Create: `frontend/src/lib/serverUrl.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/lib/auth.ts`
- Modify: `frontend/src/api/backup.ts`

**Interfaces:**
- Produces: `isNative(): boolean`, `getApiBase(): string`,
  `bootstrapServerUrl(): Promise<void>`, `getServerUrl(): string | null`,
  `setServerUrl(url: string): Promise<void>`, `clearServerUrl(): Promise<void>`,
  `useServerState(): { ready: boolean; serverUrl: string | null }`.
  Task 3 (`ServerGate`, `ServerSetupScreen`, the Settings "change server"
  option) consumes `bootstrapServerUrl`, `useServerState`, `setServerUrl`,
  `clearServerUrl`, `isNative`.

This is the highest-risk task in this plan for the "must not change web
behavior" constraint — `getApiBase()` is called from every single network
request the app makes. Read `frontend/src/lib/auth.ts` in full before
starting (not just the two functions being changed) to confirm you're not
missing a `fetch("/api/...")` call site this task's Step 3 doesn't
already enumerate.

- [ ] **Step 1: Create `lib/serverUrl.ts`**

Create `frontend/src/lib/serverUrl.ts`:

```typescript
import { useSyncExternalStore } from "react";
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

/**
 * Where a native (Android/iOS) build's backend actually lives.
 *
 * Aurum is self-hosted — every installer runs their own backend, there is
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

/** Called once by ServerGate on mount. On the web this just marks state
 * ready immediately (there's nothing to load) — on native, it loads
 * whatever server URL was saved on a previous launch, if any. */
export async function bootstrapServerUrl(): Promise<void> {
  if (!isNative()) {
    setState({ ready: true });
    return;
  }
  const { value } = await Preferences.get({ key: SERVER_URL_KEY });
  setState({ ready: true, serverUrl: value ?? null });
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
```

- [ ] **Step 2: Wire `api/client.ts`**

Modify `frontend/src/api/client.ts` — replace the import line and remove
the constant:

```typescript
import { clearSession, getAccessToken, refreshAccessToken } from "@/lib/auth";
import { getApiBase } from "@/lib/serverUrl";

export class ApiError extends Error {
```

(The `const API_BASE = "/api";` line is deleted — replaced by a live call
to `getApiBase()` at the point of use, below.)

Replace `doFetch`:

```typescript
function doFetch(path: string, init: RequestInit | undefined, accessToken: string | null): Promise<Response> {
  return fetch(`${getApiBase()}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    ...init,
  });
}
```

- [ ] **Step 3: Wire `lib/auth.ts`'s five raw `fetch` calls**

Modify `frontend/src/lib/auth.ts` — add the import:

```typescript
import { getApiBase } from "@/lib/serverUrl";
```

Then update every one of these five call sites (confirmed via
`grep -n 'fetch("/api' frontend/src/lib/auth.ts` before writing this
plan — there are exactly five, no more, no fewer) to build its URL from
`getApiBase()` instead of the hardcoded `"/api/..."` string literal.
Change ONLY the URL argument on each `fetch(...)` call — leave every
other argument (headers, method, body) exactly as it is:

- `fetchCurrentUser`: `fetch("/api/auth/me", ...)` → `` fetch(`${getApiBase()}/auth/me`, ...) ``
- `login`: `fetch("/api/auth/login", ...)` → `` fetch(`${getApiBase()}/auth/login`, ...) ``
- `register`: `fetch("/api/auth/register", ...)` → `` fetch(`${getApiBase()}/auth/register`, ...) ``
- `logout`: `fetch("/api/auth/logout", ...)` → `` fetch(`${getApiBase()}/auth/logout`, ...) ``
- `refreshAccessToken`'s inner IIFE: `fetch("/api/auth/refresh", ...)` → `` fetch(`${getApiBase()}/auth/refresh`, ...) ``

- [ ] **Step 4: Wire `api/backup.ts`'s two raw `fetch` calls**

Modify `frontend/src/api/backup.ts` — add the import:

```typescript
import { getApiBase } from "@/lib/serverUrl";
```

Update both `fetch("/api/backup/export", ...)` call sites (the initial
request and the retry-after-refresh request, added in an earlier plan) to
`` fetch(`${getApiBase()}/backup/export`, ...) ``, same one-argument-only
change as Step 3.

- [ ] **Step 5: Verify the build**

Run: `cd frontend && npm run build`
Expected: succeeds cleanly. Then confirm no hardcoded `/api` literal
remains anywhere it shouldn't:
`grep -rn '"/api' frontend/src` should return NOTHING (every occurrence
converted to a `getApiBase()`-based template string) — if this grep finds
anything, a call site was missed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/serverUrl.ts frontend/src/api/client.ts frontend/src/lib/auth.ts frontend/src/api/backup.ts
git commit -m "Ввести динамический адрес backend для нативной сборки"
```

---

## Task 3: Server setup screen, gate, and a way to change it later

**Files:**
- Create: `frontend/src/components/auth/ServerSetupScreen.tsx`
- Create: `frontend/src/components/auth/ServerGate.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Interfaces:**
- Consumes: `bootstrapServerUrl`, `useServerState`, `setServerUrl`,
  `clearServerUrl`, `isNative` (Task 2).

- [ ] **Step 1: Add i18n keys**

Modify `frontend/src/lib/i18n.ts` — add to the `ru` block (place near the
existing `auth.*` keys, since this is the same first-run-gate family):

```typescript
  "serverSetup.subtitle": "Подключение к серверу",
  "serverSetup.urlLabel": "Адрес сервера",
  "serverSetup.checking": "Проверка…",
  "serverSetup.continueButton": "Продолжить",
  "serverSetup.errorInvalidUrl": "Введите полный адрес, например https://aurum.example.com",
  "serverSetup.errorUnreachable": "Не удалось подключиться к этому адресу. Проверьте, что сервер запущен и доступен.",
  "settings.changeServer": "Сменить сервер",
  "settings.changeServerConfirm": "Вы уверены? Приложение перезапустится и запросит новый адрес сервера.",
```

Add the identical key set to the `en` block:

```typescript
  "serverSetup.subtitle": "Connect to your server",
  "serverSetup.urlLabel": "Server address",
  "serverSetup.checking": "Checking…",
  "serverSetup.continueButton": "Continue",
  "serverSetup.errorInvalidUrl": "Enter a full address, e.g. https://aurum.example.com",
  "serverSetup.errorUnreachable": "Couldn't connect to that address. Check that the server is running and reachable.",
  "settings.changeServer": "Change server",
  "settings.changeServerConfirm": "Are you sure? The app will restart and ask for a new server address.",
```

- [ ] **Step 2: Create `ServerSetupScreen.tsx`**

Create `frontend/src/components/auth/ServerSetupScreen.tsx`:

```tsx
import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { setServerUrl } from "@/lib/serverUrl";
import { useTranslation } from "@/lib/i18n";

type Status = "idle" | "checking" | "invalid" | "unreachable";

/** Shown by ServerGate on native builds before anything else — a
 * self-hosted backend has no fixed address the app could ship with, so
 * the first thing a fresh native install needs is the user's own
 * server's URL. Verifies the address actually reaches a real Aurum
 * backend (via /api/health) before saving it via lib/serverUrl.ts's
 * setServerUrl(), so a typo shows an error immediately instead of
 * silently breaking every request afterward. */
export function ServerSetupScreen() {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    let origin: string;
    try {
      origin = new URL(url.trim()).origin;
    } catch {
      setStatus("invalid");
      return;
    }

    setStatus("checking");
    try {
      const response = await fetch(`${origin}/api/health`);
      if (!response.ok) {
        setStatus("unreachable");
        return;
      }
    } catch {
      setStatus("unreachable");
      return;
    }

    await setServerUrl(origin);
    // No further state update needed here — ServerGate re-renders
    // reactively the moment setServerUrl() changes lib/serverUrl.ts's
    // state, the same pattern AuthScreen relies on for login/register.
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
            <span className="text-xs text-text-muted">{t("serverSetup.subtitle")}</span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            <div>
              <Label htmlFor="server-url">{t("serverSetup.urlLabel")}</Label>
              <Input
                id="server-url"
                name="server-url"
                type="url"
                inputMode="url"
                autoCapitalize="none"
                autoCorrect="off"
                placeholder="https://aurum.example.com"
                autoFocus
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </div>

            {status === "invalid" && <p className="text-sm text-danger">{t("serverSetup.errorInvalidUrl")}</p>}
            {status === "unreachable" && <p className="text-sm text-danger">{t("serverSetup.errorUnreachable")}</p>}

            <Button type="submit" className="w-full" disabled={status === "checking"}>
              {status === "checking" ? t("serverSetup.checking") : t("serverSetup.continueButton")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Create `ServerGate.tsx`**

Create `frontend/src/components/auth/ServerGate.tsx`:

```tsx
import { type ReactNode, useEffect } from "react";
import { Logo } from "@/components/layout/Logo";
import { ServerSetupScreen } from "@/components/auth/ServerSetupScreen";
import { bootstrapServerUrl, isNative, useServerState } from "@/lib/serverUrl";

/** Wraps LoginGate/App, outermost — must resolve before anything else,
 * since even LoginGate's own session bootstrap makes an API call. On the
 * web this is a pure passthrough: `isNative()` is false, there's always a
 * same-origin nginx proxy at /api, and nothing here ever blocks
 * rendering. Only on a native build does this show ServerSetupScreen
 * until a backend address has been configured (see lib/serverUrl.ts). */
export function ServerGate({ children }: { children: ReactNode }) {
  const { ready, serverUrl } = useServerState();

  useEffect(() => {
    bootstrapServerUrl();
    // Deliberately runs once on mount only — later changes are handled by
    // useServerState() re-rendering this component directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (isNative() && !serverUrl) {
    return <ServerSetupScreen />;
  }

  return <>{children}</>;
}
```

- [ ] **Step 4: Wire `ServerGate` into `main.tsx`**

Modify `frontend/src/main.tsx` — replace:

```typescript
import { LoginGate } from "@/components/auth/LoginGate";
```

with:

```typescript
import { LoginGate } from "@/components/auth/LoginGate";
import { ServerGate } from "@/components/auth/ServerGate";
```

and replace:

```tsx
      <BrowserRouter>
        <LoginGate>
          <App />
        </LoginGate>
      </BrowserRouter>
```

with:

```tsx
      <BrowserRouter>
        <ServerGate>
          <LoginGate>
            <App />
          </LoginGate>
        </ServerGate>
      </BrowserRouter>
```

(`ServerGate` goes OUTSIDE `LoginGate` — a server address must be known
before `LoginGate`'s own session bootstrap can make its first API call.)

- [ ] **Step 5: Add a "change server" option to Settings (native only)**

Read `frontend/src/pages/SettingsPage.tsx` first to find where a similar
standalone action button already lives (e.g. near any existing
danger-zone-style action, if one exists) and match its exact layout
pattern rather than inventing a new one. Add, gated on `isNative()` so it
never appears on the web (there is nothing to change there):

```tsx
import { isNative, clearServerUrl } from "@/lib/serverUrl";
```

and, in the component body, something in the shape of:

```tsx
{isNative() && (
  <Button
    variant="secondary"
    onClick={() => {
      if (window.confirm(t("settings.changeServerConfirm"))) {
        void clearServerUrl();
      }
    }}
  >
    {t("settings.changeServer")}
  </Button>
)}
```

Placed as its own section/card, following whatever sectioning convention
`SettingsPage.tsx` already uses for its other settings groups (currency,
language, thresholds, etc.) — read the file and match its structure;
don't guess the exact surrounding JSX, the file is substantial and this
plan hasn't reproduced it in full. Clearing the server URL causes
`ServerGate` to reactively fall back to `ServerSetupScreen` immediately
(no manual navigation needed) since `App` (and everything inside it,
including this very page) unmounts the moment `serverUrl` becomes `null`.

- [ ] **Step 6: Verify the build**

Run: `cd frontend && npm run build`
Expected: succeeds cleanly.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/auth/ServerSetupScreen.tsx frontend/src/components/auth/ServerGate.tsx frontend/src/main.tsx frontend/src/lib/i18n.ts frontend/src/pages/SettingsPage.tsx
git commit -m "Добавить экран настройки сервера для нативной сборки"
```

---

## Task 4: App icon and splash screen

**Files:**
- Create: `frontend/assets/icon.png` (and/or `icon-foreground.png`/`icon-background.png`)
- Create: `frontend/assets/splash.png`
- Modify: `frontend/android/` (generated by `@capacitor/assets`, not
  hand-edited)

**Interfaces:** none.

- [ ] **Step 1: Produce a source icon image**

`frontend/public/favicon.svg` is Aurum's real, existing brand mark (a
gold coin with an "A" monogram — see `frontend/src/components/layout/Logo.tsx`'s
docstring, which says the two are kept in sync) — use it as the source,
not a placeholder. `@capacitor/assets` needs raster PNG input (1024×1024
for the icon, 2732×2732 for the splash screen), so the SVG needs
rasterizing first. Try, in order:

1. If `rsvg-convert`, `inkscape`, or ImageMagick's `convert`/`magick` is
   available on the machine running this task, use it directly:
   `rsvg-convert -w 1024 -h 1024 frontend/public/favicon.svg -o frontend/assets/icon.png`
   (adjust for whichever tool is actually present).
2. If none of those are available (confirmed absent on this project's own
   development machine during this plan's research), install `sharp` as
   a temporary local tool and rasterize via a short Node script:
   ```bash
   cd frontend && npm install --no-save sharp
   node -e "
     const sharp = require('sharp');
     const fs = require('fs');
     const svg = fs.readFileSync('public/favicon.svg');
     sharp(svg, { density: 384 }).resize(1024, 1024).png().toFile('assets/icon.png')
       .then(() => sharp(svg, { density: 384 }).resize(1024, 1024).png().toFile('assets/icon-foreground.png'));
   "
   ```
   (`density: 384` gives sharp enough source resolution to downscale
   cleanly to 1024px without visible aliasing on the vector's thin
   stroke widths — adjust if the rendered result looks wrong.) Uninstall
   `sharp` afterward if it isn't otherwise needed (`--no-save` above
   already keeps it out of `package.json`, but it will still sit in
   `node_modules` until reinstalled clean — harmless either way, just
   don't commit a `package.json`/`package-lock.json` change for it).
3. For the splash screen, the simplest correct choice given there's no
   dedicated splash artwork is a plain background color (matching the
   app's own `--surface-0` token/light background, check
   `frontend/src/index.css` or `frontend/src/lib/theme.ts` for the exact
   hex value already used elsewhere) with the same icon centered — either
   compose this with `sharp` (create a 2732×2732 canvas of that color,
   composite the icon at a reasonable scale in the center) or use
   `@capacitor/assets`' own splash generation, which can do this
   composition automatically from a single icon + a specified background
   color — check its current CLI flags/config options for this (its
   generated config file, if the tool creates one, is the place to set
   this — don't hand-edit generated Android XML resources directly).

- [ ] **Step 2: Generate the Android asset set**

```bash
cd frontend
npx @capacitor/assets generate --android
```

This reads the source images from `frontend/assets/` (Capacitor's
default convention) and writes every required density/shape variant
directly into `frontend/android/app/src/main/res/`.

- [ ] **Step 3: Verify**

There is no way to visually confirm the generated icons render correctly
without an emulator/device (not available in this environment) — confirm
instead that the generator command completed without error and that
`frontend/android/app/src/main/res/mipmap-*/` directories now contain
updated icon files (check file modification timestamps or `git status`
showing them as changed) rather than claiming visual verification that
didn't happen.

- [ ] **Step 4: Commit**

```bash
git add frontend/assets/ frontend/android/
git commit -m "Сгенерировать иконку и заставку приложения из фирменного знака"
```

---

## Task 5: CI job to build and publish a debug APK

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none.

- [ ] **Step 1: Add the `android-build` job**

Modify `.github/workflows/ci.yml` — append a new job after the existing
`frontend-build` job (keep both existing jobs, `backend-tests` and
`frontend-build`, completely unchanged):

```yaml
  android-build:
    runs-on: ubuntu-latest
    needs: frontend-build
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run build
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - uses: android-actions/setup-android@v3
      - run: npx cap sync android
      - name: Build debug APK
        working-directory: frontend/android
        run: ./gradlew assembleDebug
      - uses: actions/upload-artifact@v4
        with:
          name: aurum-debug-apk
          path: frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

(`needs: frontend-build` means this job only runs after the existing
type-check/build job passes — no point spending CI minutes on an Android
build if the web app itself doesn't even compile. `android-actions/setup-android@v3`
installs the Android SDK platform/build-tools Gradle needs; `actions/setup-java@v4`
with Temurin 17 matches what Capacitor 7's Gradle configuration expects.)

- [ ] **Step 2: Verify the YAML is well-formed**

This can't be verified by actually running the workflow from here (no
GitHub Actions runner available locally) — at minimum, confirm the file
parses as valid YAML:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "valid YAML"
```

Report this as syntax-only verification, not a confirmation the job
actually succeeds — that only happens once this is pushed and GitHub
Actions actually runs it, which is out of this plan's own ability to
verify and should be checked by the user after this branch merges.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Добавить сборку debug-apk для Android в CI"
```

---

## Plan Self-Review Notes

- **Spec coverage:** implements both confirmed design decisions (server-URL
  setup screen, CI APK builds) plus the necessary supporting
  infrastructure (Capacitor scaffold, dynamic API base, icon/splash) —
  nothing in the confirmed design was left unaddressed.
- **Type/interface consistency:** `lib/serverUrl.ts`'s exports
  (`isNative`, `getApiBase`, `bootstrapServerUrl`, `getServerUrl`,
  `setServerUrl`, `clearServerUrl`, `useServerState`) are consumed with
  matching names/signatures across Task 2 (client.ts, auth.ts, backup.ts)
  and Task 3 (ServerGate, ServerSetupScreen, SettingsPage) — checked
  against each task's own code blocks above, not just asserted.
- **No placeholders:** every step contains complete, real code except
  Task 4's icon/splash generation and Task 3 Step 5's Settings
  integration, both of which explicitly say WHY (no way to visually
  verify generated icons without a device; `SettingsPage.tsx`'s existing
  structure needs to be read and matched, not guessed at from outside)
  rather than silently hand-waving past a real gap.
- **Verification honesty:** every task's Step explicitly separates what
  CAN be verified in this environment (TypeScript build, grep-based
  completeness checks, YAML syntax validity) from what CANNOT (an actual
  compiled/running Android app, generated icons' visual correctness, CI
  actually succeeding on GitHub's runners) — consistent with this
  session's established practice of never claiming verification that
  didn't happen.

---

## Next Plan

None currently planned — this closes out the original request that
started this whole session. Natural follow-ups if desired later: an iOS
build (`@capacitor/ios`, same `getApiBase()`/`ServerGate` infrastructure
already supports it with no changes), a Play Store release build/signing
pipeline (this plan only produces unsigned debug APKs), or native
features explicitly deferred here (biometric lock, push notifications,
deep links).
