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
  // Опционально: не у каждого потребителя (например, строки-варианты в
  // Select.tsx) нужна иконка слева — раньше было обязательным полем, пока
  // единственным потребителем был MobileTabBar.
  icon?: LucideIcon;
  label: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  trailing?: ReactNode;
}

export function GroupedListItem({ icon: Icon, label, onClick, disabled = false, trailing }: GroupedListItemProps) {
  // Строго undefined, а не `??` — вызывающий код должен уметь явно
  // передать trailing={null}, чтобы совсем убрать autoi-шеврон (например,
  // Select.tsx показывает либо галочку у выбранного варианта, либо ничего
  // — обычный ChevronRight намекал бы на переход на другой экран, а не на
  // выбор значения). `??` считал бы null тем же, что и "не передали", и
  // всё равно подставлял бы шеврон — найдено при добавлении Select.tsx.
  const resolvedTrailing =
    trailing !== undefined ? trailing : !disabled && onClick ? <ChevronRight size={16} className="text-text-muted" /> : null;

  if (disabled || !onClick) {
    return (
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3 text-sm",
          disabled ? "cursor-not-allowed text-text-muted" : "text-text-primary"
        )}
      >
        {Icon && <Icon size={18} className="shrink-0" />}
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
      {Icon && <Icon size={18} className="shrink-0" />}
      <span className="flex-1 truncate">{label}</span>
      {resolvedTrailing}
    </button>
  );
}
