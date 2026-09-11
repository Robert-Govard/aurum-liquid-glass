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
