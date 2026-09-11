import type { PropsWithChildren, ReactNode } from "react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";

interface DialogProps extends PropsWithChildren {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
}

// Должно совпадать с duration-200 в классах ниже — таймер unmount'а
// ждёт ровно столько же, сколько идёт CSS-переход, иначе анимация закрытия
// либо обрежется, либо после неё будет заметная пауза с уже невидимым, но
// ещё не удалённым из DOM диалогом.
const TRANSITION_MS = 200;

export function Dialog({ open, onClose, title, children }: DialogProps) {
  const { t } = useTranslation();
  // shouldRender держит диалог в DOM ещё TRANSITION_MS после open=false —
  // без этого закрытие происходило бы мгновенно (unmount) и анимации
  // исчезновения не было бы видно вообще. visible — это то, что реально
  // переключает CSS-классы между "открыт"/"закрыт"; отдельный стейт нужен,
  // чтобы при открытии React сначала отрисовал "закрытое" состояние и лишь
  // на следующий кадр переключил его в "открытое" — иначе браузеру не от
  // чего анимировать переход (он увидел бы сразу конечное состояние).
  const [shouldRender, setShouldRender] = useState(open);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) {
      setShouldRender(true);
      const raf = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
    const timeout = setTimeout(() => setShouldRender(false), TRANSITION_MS);
    return () => clearTimeout(timeout);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!shouldRender) return null;

  // Портал в document.body: если когда-нибудь диалог окажется вложен в
  // предка с backdrop-filter (например, Card variant="glass" на будущем
  // этапе), тот создаёт containing block для fixed-потомков — без портала
  // z-[60] и позиционирование "во весь экран" ниже перестали бы работать.
  // Найдено финальным ревью этой ветки, зафиксировано превентивно.
  return createPortal(
    <div
      className={cn(
        // z-[60]: должен перекрывать нижний таб-бар MobileTabBar (z-40, см.
        // MobileTabBar.tsx) — иначе диалог (в частности сам MoreSheet,
        // который MobileTabBar открывает поверх себя) визуально оказывается
        // под таб-баром. Изначально комментарий объяснял то же самое
        // требование относительно мобильной шторки Sidebar (z-50) — она
        // была убрана в пользу MobileTabBar, требование к z-index осталось.
        "fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 transition-opacity duration-200 sm:items-center sm:p-4",
        visible ? "opacity-100" : "opacity-0"
      )}
      onClick={onClose}
    >
      <div
        className={glassSurfaceClass(
          cn(
            "max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-glass-border px-5 pt-5 pb-[calc(1.25rem+var(--safe-area-bottom))] shadow-xl transition-[transform,opacity] duration-200 sm:max-w-md sm:rounded-2xl sm:pb-5",
            // Мобильный bottom-sheet выезжает снизу; десктопный
            // центрированный modal (sm: и выше) вместо этого чуть
            // увеличивается из уменьшенного состояния — выезд снизу для
            // центра экрана выглядел бы неуместно.
            visible ? "translate-y-0 opacity-100 sm:scale-100" : "translate-y-full opacity-0 sm:translate-y-0 sm:scale-95"
          )
        )}
        onClick={(event) => event.stopPropagation()}
      >
        {/* Визуальная "хваталка" — как в нативных iOS-шторках снизу.
            Скрыта на sm: и выше, где Dialog уже не bottom-sheet, а
            центрированное модальное окно (тот же брейкпоинт, что делит
            эти два режима в контейнере-backdrop ниже). Жест смахивания
            вниз для закрытия не реализован — вне запрошенного скоупа. */}
        <div aria-hidden className="mx-auto mb-3 h-1 w-9 rounded-full bg-border sm:hidden" />
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-text-primary">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="rounded-md p-1 text-text-muted hover:bg-surface-2"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}
