# iOS-Style Mobile UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle Aurum's mobile-width (`<lg`, i.e. `<1024px`) layout — used both by the mobile browser and the Android app — with iOS-inspired navigation (bottom tab bar + "More" sheet), component visuals (grouped lists, pill switches, segmented control, bottom-sheet drag handle, larger corner radii), and an edge-swipe-back gesture, while keeping the existing Aurum "Liquid Glass" theme and leaving the desktop (`≥lg`) layout untouched.

**Architecture:** Replace the current mobile hamburger + off-canvas drawer (`Sidebar.tsx`'s mobile branch, `Topbar.tsx`'s menu button) with a fixed bottom `MobileTabBar` showing 4 primary sections plus a "More" tab that opens the remaining sections in a bottom-sheet `GroupedList`. Add two new reusable UI primitives (`GroupedList`, `Switch`) and a segmented-control rework of `PillSelector`. Add a touch-based edge-swipe-back hook that calls `navigate(-1)` when there is in-app history to go back to. All of this is pure frontend (`frontend/src/`) — no backend changes.

**Tech Stack:** React 19, react-router-dom v7, Tailwind v4 (CSS-based `@theme`, no config file), lucide-react icons. No frontend test framework exists in this repo (confirmed: `package.json` has no `test` script, no `.test.ts(x)` files anywhere) — the only automated check available is `npm run build` (`tsc -b && vite build`).

**Spec:** `docs/superpowers/specs/2026-09-11-ios-style-mobile-ui-design.md`

## Global Constraints

- Changes apply ONLY at `<lg` (`<1024px`) width — the same breakpoint already used by `Sidebar.tsx`/`Topbar.tsx` to switch between desktop and mobile layout. The `≥lg` desktop layout is not modified in any task.
- Keep the existing Aurum theme (tokens in `frontend/src/index.css`, `glassSurfaceClass` from `components/ui/GlassSurface.tsx`) — no new colors introduced. No Apple system-blue accent, no Apple typography.
- Every user-visible string goes through `frontend/src/lib/i18n.ts`, added to BOTH the `ru` and `en` blocks in the same commit.
- No browser or Android device is available in this environment — verification is `npm run build` plus code reading. Every task report must say so explicitly rather than claim visual confirmation.
- No backend changes. All work is under `frontend/`.
- `GroupedList` is used ONLY for the new "More" sheet — NOT retrofitted onto `SettingsPage` (that page is composed of purpose-built cards like `PreferencesCard`/`CurrencyCard`/`AlertThresholdsCard`/`BackupCard`, not a navigable row list; forcing the pattern there would degrade the layout, not improve it — decided during planning after reading those files).

---

### Task 1: Safe-area tokens, mobile-tab constant, i18n key, and the edge-swipe-back hook

**Files:**
- Modify: `frontend/src/index.css` (add safe-area CSS custom properties)
- Modify: `frontend/src/lib/navigation.ts` (add `MOBILE_TAB_PATHS`)
- Modify: `frontend/src/lib/i18n.ts` (add `"nav.more"` key to both `ru` and `en` blocks)
- Create: `frontend/src/hooks/useIsMobileViewport.ts`
- Create: `frontend/src/hooks/useEdgeSwipeBack.ts`
- Modify: `frontend/src/App.tsx` (wire the gesture hook in)

**Interfaces:**
- Produces: `MOBILE_TAB_PATHS: string[]` (exported from `lib/navigation.ts`) — the 4 paths, in tab-bar display order, that Task 4's `MobileTabBar` uses to pick primary tabs vs. "More" items.
- Produces: `useIsMobileViewport(): boolean` (default export is named, from `hooks/useIsMobileViewport.ts`) — `true` when viewport width is `<1024px`, reactive to resize.
- Produces: `useEdgeSwipeBack(enabled: boolean): void` (from `hooks/useEdgeSwipeBack.ts`) — attaches/detaches the swipe-back listener based on `enabled`. Must be called from a component rendered inside a Router (it uses `useNavigate`/`useNavigationType`); `App.tsx` already is (see `main.tsx`'s `<BrowserRouter>` wrapping).
- Produces: i18n key `"nav.more"` (`"Ещё"` / `"More"`) — consumed by Task 4's `MobileTabBar`/`MoreSheet`.
- Produces: CSS custom properties `--safe-area-top`, `--safe-area-bottom` on `:root` — consumed by Task 4's `MobileTabBar` and `App.tsx`'s `<main>` padding.

- [ ] **Step 1: Add safe-area CSS tokens**

In `frontend/src/index.css`, the `:root` block currently ends with:

```css
  --series-other: #898781;
}
```

Change it to:

```css
  --series-other: #898781;

  /* Отступы под системные элементы (вырез/жестовая полоса) — используются
     нижним таб-баром (MobileTabBar) и контентной областью на мобильной
     ширине. env() возвращает 0px там, где инсетов нет (обычный браузер),
     так что применять эти токены безопасно всегда, а не только в
     Android-приложении. */
  --safe-area-top: env(safe-area-inset-top, 0px);
  --safe-area-bottom: env(safe-area-inset-bottom, 0px);
}
```

This is theme-independent (no light/dark variant needed), so it does not need to be repeated in the `@media (prefers-color-scheme: dark)` or `[data-theme="dark"]` blocks further down the file.

- [ ] **Step 2: Add the mobile tab-bar path list**

In `frontend/src/lib/navigation.ts`, after the closing `];` of `NAV_ITEMS`, add:

```ts

/** Порядок путей для нижнего таб-бара на мобильной ширине (<lg) — первые
 * 4 пункта видны напрямую как вкладки, остальные NAV_ITEMS доступны через
 * вкладку "Ещё" (см. components/layout/MobileTabBar.tsx). Порядок в этом
 * массиве — порядок вкладок слева направо, а не порядок в NAV_ITEMS. */
export const MOBILE_TAB_PATHS: string[] = ["/", "/transactions", "/budget", "/accounts"];
```

- [ ] **Step 3: Add the `nav.more` i18n key to both blocks**

In `frontend/src/lib/i18n.ts`, the `ru` block has (around line 21):

```ts
  "nav.settings": "Настройки",
  "nav.comingSoon": "скоро",
```

Change to:

```ts
  "nav.settings": "Настройки",
  "nav.more": "Ещё",
  "nav.comingSoon": "скоро",
```

The `en` block has the matching pair (around line 532):

```ts
  "nav.settings": "Settings",
  "nav.comingSoon": "soon",
```

Change to:

```ts
  "nav.settings": "Settings",
  "nav.more": "More",
  "nav.comingSoon": "soon",
```

- [ ] **Step 4: Run the build to confirm the i18n type stays consistent**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors. (The `en` block is typed as `Record<keyof typeof ru, string>` in this file, so a key present in only one block would fail the build — this step's real purpose is catching that.)

- [ ] **Step 5: Create `useIsMobileViewport`**

Create `frontend/src/hooks/useIsMobileViewport.ts`:

```ts
import { useEffect, useState } from "react";

// Синхронизировано с порогом `lg` (1024px), уже используемым в
// Sidebar.tsx/Topbar.tsx для переключения между десктопным и мобильным
// layout — 1023.98px вместо 1024px, чтобы не зависеть от округления
// субпиксельной ширины окна в конкретных браузерах.
const MOBILE_QUERY = "(max-width: 1023.98px)";

export function useIsMobileViewport(): boolean {
  const [isMobile, setIsMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setIsMobile(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
```

- [ ] **Step 6: Create `useEdgeSwipeBack`**

Create `frontend/src/hooks/useEdgeSwipeBack.ts`:

```ts
import { useEffect, useRef } from "react";
import { useNavigate, useNavigationType } from "react-router-dom";

const EDGE_ZONE_PX = 24;
const SWIPE_THRESHOLD_PX = 80;

/** Свайп от левого края экрана — переход на предыдущую страницу внутри
 * приложения, как в iOS. Считает "глубину" истории сам (react-router не
 * даёт это напрямую): PUSH увеличивает счётчик, POP уменьшает, REPLACE не
 * влияет. Жест игнорируется, если возвращаться внутри приложения некуда —
 * иначе на Android свайп у самого края экрана мог бы неожиданно закрыть
 * приложение через системный жест "назад".
 */
export function useEdgeSwipeBack(enabled: boolean): void {
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const depthRef = useRef(0);

  useEffect(() => {
    if (navigationType === "PUSH") depthRef.current += 1;
    else if (navigationType === "POP") depthRef.current = Math.max(0, depthRef.current - 1);
  }, [navigationType]);

  useEffect(() => {
    if (!enabled) return;
    let tracking = false;
    let startX = 0;
    let startY = 0;

    function onTouchStart(event: TouchEvent) {
      const touch = event.touches[0];
      if (!touch || touch.clientX > EDGE_ZONE_PX || depthRef.current <= 0) return;
      tracking = true;
      startX = touch.clientX;
      startY = touch.clientY;
    }

    function onTouchEnd(event: TouchEvent) {
      if (!tracking) return;
      tracking = false;
      const touch = event.changedTouches[0];
      if (!touch) return;
      const dx = touch.clientX - startX;
      const dy = Math.abs(touch.clientY - startY);
      if (dx > SWIPE_THRESHOLD_PX && dy < dx) navigate(-1);
    }

    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchend", onTouchEnd);
    };
  }, [enabled, navigate]);
}
```

- [ ] **Step 7: Wire the gesture hook into `App.tsx`**

In `frontend/src/App.tsx`, the imports currently start with:

```tsx
import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
```

Change to:

```tsx
import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useEdgeSwipeBack } from "@/hooks/useEdgeSwipeBack";
import { useIsMobileViewport } from "@/hooks/useIsMobileViewport";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
```

(Leave `useState` in the import for now — it is still used by `mobileNavOpen` in this task; Task 4 removes it.)

And inside the `App()` function body, the line:

```tsx
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
```

Change to:

```tsx
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  useEdgeSwipeBack(useIsMobileViewport());
```

- [ ] **Step 8: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors (only the pre-existing chunk-size advisory warning, unrelated to this change).

- [ ] **Step 9: Commit**

```bash
cd frontend
git add src/index.css src/lib/navigation.ts src/lib/i18n.ts src/hooks/useIsMobileViewport.ts src/hooks/useEdgeSwipeBack.ts src/App.tsx
git commit -m "Добавить safe-area токены, свайп назад с края экрана и константу мобильных вкладок"
```

---

### Task 2: `GroupedList`/`Switch` UI primitives, applied to `AccountsPage`

**Files:**
- Create: `frontend/src/components/ui/GroupedList.tsx`
- Create: `frontend/src/components/ui/Switch.tsx`
- Modify: `frontend/src/pages/AccountsPage.tsx` (replace the native checkbox with `Switch`)

**Interfaces:**
- Consumes: `glassSurfaceClass` from `components/ui/GlassSurface.tsx` (existing), `cn` from `lib/utils` (existing).
- Produces: `GroupedList({ children }: { children: ReactNode })` and `GroupedListItem({ icon, label, onClick?, disabled?, trailing? }: { icon: LucideIcon; label: string; onClick?: () => void; disabled?: boolean; trailing?: ReactNode })`, both from `components/ui/GroupedList.tsx` — consumed by Task 4's `MobileTabBar`/`MoreSheet`.
- Produces: `Switch({ checked, onChange, disabled?, "aria-label" }: { checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; "aria-label": string })` from `components/ui/Switch.tsx`.

- [ ] **Step 1: Create `GroupedList`**

Create `frontend/src/components/ui/GroupedList.tsx`:

```tsx
import type { ReactNode } from "react";
import { ChevronRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";

interface GroupedListProps {
  children: ReactNode;
}

/** Сгруппированный список-карточка в стиле iOS Settings — используется
 * для панели "Ещё" в мобильной навигации (см. MobileTabBar.tsx).
 * Скругление rounded-2xl — то же, что и у Dialog.tsx в bottom-sheet
 * режиме, для визуальной согласованности. */
export function GroupedList({ children }: GroupedListProps) {
  return (
    <div className={glassSurfaceClass("divide-y divide-border overflow-hidden rounded-2xl border border-glass-border")}>
      {children}
    </div>
  );
}

interface GroupedListItemProps {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  trailing?: ReactNode;
}

export function GroupedListItem({ icon: Icon, label, onClick, disabled = false, trailing }: GroupedListItemProps) {
  const resolvedTrailing = trailing ?? (!disabled && onClick ? <ChevronRight size={16} className="text-text-muted" /> : null);

  if (disabled || !onClick) {
    return (
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3 text-sm",
          disabled ? "cursor-not-allowed text-text-muted" : "text-text-primary"
        )}
      >
        <Icon size={18} className="shrink-0" />
        <span className="flex-1 truncate">{label}</span>
        {resolvedTrailing}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-text-primary transition-colors hover:bg-surface-2"
    >
      <Icon size={18} className="shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      {resolvedTrailing}
    </button>
  );
}
```

- [ ] **Step 2: Create `Switch`**

Create `frontend/src/components/ui/Switch.tsx`:

```tsx
import { cn } from "@/lib/utils";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label": string;
}

/** iOS-стиль переключателя (пилюля с бегунком) — использует те же токены,
 * что и Button variant="primary" (bg-text-primary для "включено"), без
 * новых цветов. */
export function Switch({ checked, onChange, disabled, "aria-label": ariaLabel }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-text-primary" : "bg-surface-2"
      )}
    >
      <span
        className={cn(
          "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-surface-1 shadow-sm transition-transform",
          checked && "translate-x-5"
        )}
      />
    </button>
  );
}
```

- [ ] **Step 3: Use `Switch` in `AccountsPage`**

In `frontend/src/pages/AccountsPage.tsx`, add the import (alphabetical, alongside the other component imports):

```tsx
import { AccountList } from "@/components/accounts/AccountList";
import { AccountFormModal } from "@/components/accounts/AccountFormModal";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Switch } from "@/components/ui/Switch";
```

(This reorders the existing `Card`/`Button` imports next to the new `Switch` import to keep the block sorted — the rest of the imports below, e.g. `useAccounts`, are unaffected.)

Then replace:

```tsx
          <label className="mb-3 flex items-center gap-2 text-xs text-text-muted">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
              className="h-3.5 w-3.5 accent-text-primary"
            />
            {t("account.showArchived")}
          </label>
```

with:

```tsx
          <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
            <Switch checked={showArchived} onChange={setShowArchived} aria-label={t("account.showArchived")} />
            {t("account.showArchived")}
          </div>
```

- [ ] **Step 4: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/components/ui/GroupedList.tsx src/components/ui/Switch.tsx src/pages/AccountsPage.tsx
git commit -m "Добавить GroupedList и Switch, заменить чекбокс в Accounts на переключатель"
```

---

### Task 3: Component visual pass — segmented `PillSelector`, `Dialog` drag handle, larger corner radii

**Files:**
- Modify: `frontend/src/components/layout/PillSelector.tsx`
- Modify: `frontend/src/components/ui/Dialog.tsx`
- Modify: `frontend/src/components/ui/Button.tsx`
- Modify: `frontend/src/components/ui/Card.tsx`

**Interfaces:**
- `PillSelector`'s public props (`options`/`value`/`onChange`) are unchanged — every existing consumer (date/month/year/range selectors) keeps working with no call-site changes.
- `Dialog`'s public props (`open`/`onClose`/`title`/`children`) are unchanged.

- [ ] **Step 1: Rework `PillSelector` into a sliding segmented control**

Replace the full contents of `frontend/src/components/layout/PillSelector.tsx` with:

```tsx
import { cn } from "@/lib/utils";

interface PillOption<T extends string> {
  value: T;
  label: string;
}

interface PillSelectorProps<T extends string> {
  options: Array<PillOption<T>>;
  value: T;
  onChange: (value: T) => void;
}

export function PillSelector<T extends string>({ options, value, onChange }: PillSelectorProps<T>) {
  const activeIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value)
  );

  return (
    <div
      className="relative grid rounded-lg border border-border bg-surface-1 p-1"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {/* Скользящий фон активного сегмента (iOS segmented control). Ширина
          и позиция считаются через CSS grid + translateX в процентах от
          собственной ширины индикатора — не через измерение DOM
          (ref/getBoundingClientRect), поэтому работает сразу для любого
          числа вариантов без лишнего кода. */}
      <div
        aria-hidden
        className="absolute inset-y-1 left-1 rounded-md bg-surface-2 transition-transform duration-200 ease-out"
        style={{
          width: `calc((100% - 0.5rem) / ${options.length})`,
          transform: `translateX(${activeIndex * 100}%)`,
        }}
      />
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "relative z-10 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              active ? "text-text-primary" : "text-text-muted hover:text-text-primary"
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Add a drag handle to `Dialog`'s bottom-sheet panel**

In `frontend/src/components/ui/Dialog.tsx`, find:

```tsx
      <div
        className={glassSurfaceClass("max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-glass-border p-5 shadow-xl sm:max-w-md sm:rounded-2xl")}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
```

Change to:

```tsx
      <div
        className={glassSurfaceClass("max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-glass-border p-5 shadow-xl sm:max-w-md sm:rounded-2xl")}
        onClick={(event) => event.stopPropagation()}
      >
        {/* Визуальная "хваталка" — как в нативных iOS-шторках снизу.
            Скрыта на sm: и выше, где Dialog уже не bottom-sheet, а
            центрированное модальное окно (тот же брейкпоинт, что делит
            эти два режима в контейнере-backdrop ниже). Жест смахивания
            вниз для закрытия не реализован — вне запрошенного скоупа. */}
        <div aria-hidden className="mx-auto mb-3 h-1 w-9 rounded-full bg-border sm:hidden" />
        <div className="mb-4 flex items-center justify-between">
```

- [ ] **Step 3: Increase `Button`'s corner radius**

In `frontend/src/components/ui/Button.tsx`, find:

```tsx
        "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
```

Change `rounded-lg` to `rounded-xl`:

```tsx
        "inline-flex h-9 items-center justify-center gap-1.5 rounded-xl px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
```

- [ ] **Step 4: Increase `Card`'s corner radius**

In `frontend/src/components/ui/Card.tsx`, find:

```tsx
          ? glassSurfaceClass(cn("min-w-0 rounded-xl border border-glass-border shadow-sm", className))
          : cn("min-w-0 rounded-xl border border-border bg-surface-1 shadow-sm", className)
```

Change both `rounded-xl` to `rounded-2xl`:

```tsx
          ? glassSurfaceClass(cn("min-w-0 rounded-2xl border border-glass-border shadow-sm", className))
          : cn("min-w-0 rounded-2xl border border-border bg-surface-1 shadow-sm", className)
```

- [ ] **Step 5: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/components/layout/PillSelector.tsx src/components/ui/Dialog.tsx src/components/ui/Button.tsx src/components/ui/Card.tsx
git commit -m "Обновить визуал компонентов под iOS-конвенции (segmented control, drag handle, скругления)"
```

---

### Task 4: Bottom tab bar + "More" sheet, remove the old hamburger/drawer navigation

**Files:**
- Create: `frontend/src/components/layout/MobileTabBar.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (remove the mobile off-canvas drawer branch and its props)
- Modify: `frontend/src/components/layout/Topbar.tsx` (remove the hamburger button and its prop)
- Modify: `frontend/src/App.tsx` (remove `mobileNavOpen` state, render `MobileTabBar`, add bottom padding to `<main>`)
- Modify: `frontend/src/lib/i18n.ts` (remove the now-unused `sidebar.closeMenu` and `topbar.openMenu` keys, both blocks)

**Interfaces:**
- Consumes: `MOBILE_TAB_PATHS`, `NAV_ITEMS` from `lib/navigation.ts` (Task 1 / pre-existing); `GroupedList`/`GroupedListItem` from `components/ui/GroupedList.tsx` (Task 2); `Dialog` from `components/ui/Dialog.tsx` (pre-existing, drag handle added in Task 3); `"nav.more"` i18n key (Task 1); `useIsMobileViewport`, `useEdgeSwipeBack` already wired into `App.tsx` (Task 1).
- Produces: `MobileTabBar` component (default export style: named export `MobileTabBar`, no props) — rendered once in `App.tsx`.

- [ ] **Step 1: Create `MobileTabBar`**

Create `frontend/src/components/layout/MobileTabBar.tsx`:

```tsx
import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Dialog } from "@/components/ui/Dialog";
import { GroupedList, GroupedListItem } from "@/components/ui/GroupedList";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { useTranslation } from "@/lib/i18n";
import { MOBILE_TAB_PATHS, NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const TAB_ITEMS = MOBILE_TAB_PATHS.map((path) => NAV_ITEMS.find((item) => item.to === path)!);
const MORE_ITEMS = NAV_ITEMS.filter((item) => !MOBILE_TAB_PATHS.includes(item.to));

function isItemActive(pathname: string, to: string): boolean {
  return to === "/" ? pathname === "/" : pathname.startsWith(to);
}

/** Нижний таб-бар — мобильная навигация (<lg), заменяет собой прежнее
 * гамбургер-меню + выезжающую шторку (см. Sidebar.tsx/Topbar.tsx). 4
 * самых частых раздела видны напрямую, остальные NAV_ITEMS — через
 * вкладку "Ещё", которая открывает GroupedList в Dialog-шторке снизу. */
export function MobileTabBar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);

  const isMoreActive = MORE_ITEMS.some((item) => isItemActive(location.pathname, item.to));

  return (
    <>
      <nav
        className={glassSurfaceClass(
          "fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t border-glass-border pb-[var(--safe-area-bottom)] lg:hidden"
        )}
      >
        {TAB_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(location.pathname, item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
                active ? "text-text-primary" : "text-text-muted"
              )}
            >
              <Icon size={22} />
              <span>{t(item.labelKey)}</span>
            </NavLink>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className={cn(
            "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
            isMoreActive ? "text-text-primary" : "text-text-muted"
          )}
        >
          <MoreHorizontal size={22} />
          <span>{t("nav.more")}</span>
        </button>
      </nav>

      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
        <GroupedList>
          {MORE_ITEMS.map((item) => {
            const Icon = item.icon;
            if (item.disabled) {
              return (
                <GroupedListItem
                  key={item.to}
                  icon={Icon}
                  label={t(item.labelKey)}
                  disabled
                  trailing={<span className="text-[10px] text-text-muted">{t("nav.comingSoon")}</span>}
                />
              );
            }
            return (
              <GroupedListItem
                key={item.to}
                icon={Icon}
                label={t(item.labelKey)}
                onClick={() => {
                  navigate(item.to);
                  setMoreOpen(false);
                }}
              />
            );
          })}
        </GroupedList>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 2: Remove the mobile drawer from `Sidebar.tsx`**

Replace the full contents of `frontend/src/components/layout/Sidebar.tsx` with:

```tsx
import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";

interface NavListProps {
  collapsed: boolean;
}

function NavList({ collapsed }: NavListProps) {
  const { t } = useTranslation();

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-2">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const label = t(item.labelKey);
        if (item.disabled) {
          return (
            <span
              key={item.to}
              title={collapsed ? `${label} (${t("nav.comingSoon")})` : undefined}
              className={cn(
                "flex cursor-not-allowed items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted",
                collapsed && "justify-center px-0"
              )}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && (
                <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                  <span className="truncate">{label}</span>
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none">
                    {t("nav.comingSoon")}
                  </span>
                </span>
              )}
            </span>
          );
        }

        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-2 hover:text-text-primary",
                collapsed && "justify-center px-0",
                isActive && "bg-surface-2 text-text-primary"
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        );
      })}
    </nav>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

/** Desktop-only (`lg:flex`) постоянная боковая панель. Мобильная
 * off-canvas версия этого компонента убрана — на <lg навигация теперь
 * MobileTabBar (см. App.tsx). */
export function Sidebar({ collapsed, onToggleCollapsed }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside
      className={glassSurfaceClass(
        cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-glass-border transition-[width] duration-150 lg:flex",
          collapsed ? "w-[72px]" : "w-56"
        )
      )}
    >
      {collapsed ? (
        // Collapsed: the logo doubles as an "expand" button — the sidebar
        // has no visible label to click in this state, so the icon itself
        // needs to be the way back to the full menu.
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={t("sidebar.expandMenu")}
          className="flex items-center justify-center gap-2 px-0 py-4 hover:opacity-80"
        >
          <Logo size={24} />
        </button>
      ) : (
        <div className="flex items-center gap-2 px-4 py-4">
          <Logo size={24} />
          <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
        </div>
      )}
      <NavList collapsed={collapsed} />
      <div className="border-t border-border p-2.5">
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={collapsed ? t("sidebar.expandMenu") : t("sidebar.collapseMenu")}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted hover:bg-surface-2 hover:text-text-primary",
            collapsed && "justify-center px-0"
          )}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          {!collapsed && <span>{t("sidebar.collapse")}</span>}
        </button>
      </div>
    </aside>
  );
}
```

(Removed: the `X`/`useEffect` imports, the `mobileOpen`/`onCloseMobile` props, the `onNavigate` prop on `NavList`, the Escape-key listener, and the entire "Mobile: off-canvas drawer" JSX block.)

- [ ] **Step 3: Remove the hamburger button from `Topbar.tsx`**

Replace the full contents of `frontend/src/components/layout/Topbar.tsx` with:

```tsx
import { LogOut } from "lucide-react";
import { useLocation } from "react-router-dom";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { logout, useAuthState } from "@/lib/auth";

export function Topbar() {
  const location = useLocation();
  const { t } = useTranslation();
  const { user, accessToken } = useAuthState();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className={glassSurfaceClass("sticky top-0 z-30 flex items-center gap-3 border-b border-glass-border px-4 py-3.5 sm:px-6 lg:px-8")}>
      <h1 className="text-lg font-semibold text-text-primary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</h1>
      {accessToken && (
        // Gated on accessToken (not user) — login()/register() in auth.ts
        // set the access token BEFORE /auth/me resolves, so LoginGate
        // (which only checks accessToken) can already be showing the app
        // while `user` is still null. Gating this container on `user`
        // would hide the logout button entirely until a reload in that
        // window; gating on accessToken keeps it available as soon as
        // there's a session to log out of, while the email itself still
        // waits for `user` to actually be populated.
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* Hidden below sm: the header is already tight on a phone
              screen with the page title, and the logout icon alone is
              enough to act on there — the email is a nice-to-have
              identity check, not something a mobile user needs visible
              at all times. */}
          {user && (
            <span className="hidden truncate text-xs text-text-muted sm:inline" title={user.email}>
              {user.email}
            </span>
          )}
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

(Removed: the `Menu` import, the `TopbarProps`/`onOpenMobileNav` prop, the hamburger `<button>`, and updated the comment that referenced it.)

- [ ] **Step 4: Update `App.tsx`**

In `frontend/src/App.tsx`, remove the now-unused `useState` import and `mobileNavOpen` state, render `MobileTabBar`, and add bottom padding to `<main>` for mobile.

Change the import block from (as left by Task 1):

```tsx
import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useEdgeSwipeBack } from "@/hooks/useEdgeSwipeBack";
import { useIsMobileViewport } from "@/hooks/useIsMobileViewport";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
```

to:

```tsx
import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import { MobileTabBar } from "@/components/layout/MobileTabBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useEdgeSwipeBack } from "@/hooks/useEdgeSwipeBack";
import { useIsMobileViewport } from "@/hooks/useIsMobileViewport";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
```

Change the state declarations from:

```tsx
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  useEdgeSwipeBack(useIsMobileViewport());
```

to:

```tsx
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  useEdgeSwipeBack(useIsMobileViewport());
```

Change the JSX from:

```tsx
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMobileNav={() => setMobileNavOpen(true)} />
        <main className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
          <Routes>
```

to:

```tsx
      <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed(!collapsed)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-6xl px-4 py-5 pb-[calc(4.5rem+var(--safe-area-bottom))] sm:px-6 sm:py-6 lg:px-8 lg:pb-6">
          <Routes>
```

And immediately after the closing `</div>` that follows the `</Routes></main>` block (i.e. right before the final closing `</div>` of the component's top-level `<div className="flex min-h-screen">`), add `<MobileTabBar />` as the last child:

```tsx
        </main>
      </div>
      <MobileTabBar />
    </div>
  );
}
```

(This replaces what was previously just `</main></div></div>);}` at the end of the file.)

- [ ] **Step 5: Remove the now-unused i18n keys**

`sidebar.closeMenu` and `topbar.openMenu` were only used by the mobile drawer's close button and the hamburger button, both removed in Steps 2-3. Grep to confirm before deleting:

Run: `cd frontend && grep -rn "sidebar.closeMenu\|topbar.openMenu" src/`
Expected: no matches outside `src/lib/i18n.ts` itself.

In `frontend/src/lib/i18n.ts`, `ru` block, remove the line `"sidebar.closeMenu": "Закрыть меню",` and the line `"topbar.openMenu": "Открыть меню",`. In the `en` block, remove the matching `"sidebar.closeMenu": "Close menu",` and `"topbar.openMenu": "Open menu",` lines.

- [ ] **Step 6: Run the build**

Run: `cd frontend && npm run build`
Expected: succeeds with no new errors.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/components/layout/MobileTabBar.tsx src/components/layout/Sidebar.tsx src/components/layout/Topbar.tsx src/App.tsx src/lib/i18n.ts
git commit -m "Заменить мобильную навигацию на нижний таб-бар с панелью Ещё"
```

---

## Self-Review Notes

- **Spec coverage:** navigation (tab bar + More sheet) → Task 4; safe-area → Task 1 + consumed in Task 4; component visuals (GroupedList, Switch, PillSelector, Dialog handle, radii) → Tasks 2-3; gesture → Task 1. The one spec item deliberately dropped (`GroupedList` on `SettingsPage`) is called out in Global Constraints with its reasoning, not silently omitted.
- **Placeholder scan:** every step has literal, complete code — no "add appropriate styling" or "similar to Task N" placeholders.
- **Type consistency:** `GroupedListItem`'s props (`icon`, `label`, `onClick?`, `disabled?`, `trailing?`) are defined once in Task 2 and used with the same names in Task 4. `MOBILE_TAB_PATHS: string[]` (Task 1) and `NAV_ITEMS` (pre-existing, `to: string`) are compared by plain string equality in Task 4 — no type mismatch. `Switch`'s `onChange: (checked: boolean) => void` accepts `AccountsPage`'s `setShowArchived` (a `Dispatch<SetStateAction<boolean>>`) directly, since the latter can always be called with a plain `boolean` argument.
- **No task leaves the build broken:** each task ends with its own `npm run build` gate before commit.
