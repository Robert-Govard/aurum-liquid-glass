import type { PropsWithChildren, ReactNode } from "react";
import { useEffect } from "react";
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

export function Dialog({ open, onClose, title, children }: DialogProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

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
        "fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      )}
      onClick={onClose}
    >
      <div
        className={glassSurfaceClass("max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-glass-border px-5 pt-5 pb-[calc(1.25rem+var(--safe-area-bottom))] shadow-xl sm:max-w-md sm:rounded-2xl sm:pb-5")}
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
