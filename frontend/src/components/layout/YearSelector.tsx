import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface YearSelectorProps {
  years: number[];
  year: number;
  onChange: (year: number) => void;
}

/** Compact dropdown, most recent year first — sits to the right of
 * MonthSelector instead of competing with it as a second row of pills. */
export function YearSelector({ years, year, onChange }: YearSelectorProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const sortedYears = [...years].sort((a, b) => b - a);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-3 text-sm font-medium text-text-primary transition-colors hover:bg-surface-2"
      >
        {year}
        <ChevronDown size={14} className={cn("text-text-muted transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 top-full z-20 mt-1.5 max-h-64 w-24 overflow-y-auto rounded-lg border border-border bg-surface-1 py-1 shadow-lg"
        >
          {sortedYears.map((value) => {
            const active = value === year;
            return (
              <li key={value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(value);
                    setOpen(false);
                  }}
                  className={cn(
                    "block w-full px-3 py-1.5 text-left text-sm transition-colors",
                    active ? "bg-surface-2 font-semibold text-text-primary" : "text-text-secondary hover:bg-surface-2"
                  )}
                >
                  {value}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
