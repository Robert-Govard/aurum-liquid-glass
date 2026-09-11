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
