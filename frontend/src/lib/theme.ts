import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "aurum:theme";
// Kept in sync by hand with index.css's --surface-0 light/dark values —
// same pair the anti-FOUC inline script in index.html uses.
const SURFACE_0 = { light: "#f9f9f7", dark: "#0d0d0d" };

function readInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return "system";
}

/** Mirrors what index.html's inline script does on first load — called
 * again on every setTheme() so switching "system" while the OS is (say)
 * dark takes effect immediately instead of waiting for the next reload. */
function applyTheme(theme: Theme): void {
  if (theme === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }

  const isDark =
    theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", isDark ? SURFACE_0.dark : SURFACE_0.light);
}

let currentTheme: Theme = readInitialTheme();
const listeners = new Set<() => void>();

// The system-preference case needs no listener of its own — index.css's
// `@media (prefers-color-scheme: dark)` re-evaluates live on its own. This
// only exists to keep the <meta name="theme-color"> in step while the user
// has "system" selected and their OS theme changes mid-session.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (currentTheme === "system") applyTheme(currentTheme);
});

export function getTheme(): Theme {
  return currentTheme;
}

export function setTheme(theme: Theme): void {
  if (theme === currentTheme) return;
  currentTheme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => currentTheme);
  return { theme, setTheme };
}
