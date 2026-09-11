import { useEffect, useRef } from "react";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";

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
  const location = useLocation();
  const depthRef = useRef(0);

  useEffect(() => {
    if (navigationType === "PUSH") depthRef.current += 1;
    else if (navigationType === "POP") depthRef.current = Math.max(0, depthRef.current - 1);
    // REPLACE: leave depth unchanged. Keyed on location.key (not just
    // navigationType) because React Router gives every history entry a
    // unique key, including consecutive entries of the same navigation
    // type — keying on navigationType alone made React skip this effect
    // on two PUSHes or two POPs in a row (Object.is-equal dependency),
    // desyncing depthRef from the real history depth. Found in review.
  }, [location.key, navigationType]);

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
