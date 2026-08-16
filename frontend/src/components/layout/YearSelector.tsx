import { cn } from "@/lib/utils";

interface YearSelectorProps {
  years: number[];
  year: number;
  onChange: (year: number) => void;
}

export function YearSelector({ years, year, onChange }: YearSelectorProps) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {years.map((value) => {
        const active = value === year;
        return (
          <button
            key={value}
            type="button"
            onClick={() => onChange(value)}
            className={cn(
              "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
              active
                ? "border-text-primary bg-text-primary text-surface-1"
                : "border-border bg-surface-1 text-text-secondary hover:bg-surface-2"
            )}
          >
            {value}
          </button>
        );
      })}
    </div>
  );
}
