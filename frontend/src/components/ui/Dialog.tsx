import type { PropsWithChildren, ReactNode } from "react";
import { useEffect } from "react";
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

  return (
    <div
      className={cn(
        // z-[60]: должен перекрывать мобильную шторку Sidebar (z-50, см.
        // Sidebar.tsx) — иначе диалог, открытый при открытой шторке,
        // визуально оказывается под ней. Баг, найденный при аудите UI.
        "fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      )}
      onClick={onClose}
    >
      <div
        className={glassSurfaceClass("max-h-[90vh] w-full overflow-y-auto rounded-t-2xl p-5 shadow-xl sm:max-w-md sm:rounded-2xl")}
        onClick={(event) => event.stopPropagation()}
      >
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
    </div>
  );
}
