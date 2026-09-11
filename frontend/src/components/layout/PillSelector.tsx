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
