import { cn } from "@/lib/utils";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label": string;
}

/** iOS-стиль переключателя (пилюля с бегунком) — использует те же токены,
 * что и Button variant="primary" (bg-text-primary для "включено"), без
 * новых цветов. */
export function Switch({ checked, onChange, disabled, "aria-label": ariaLabel }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-text-primary" : "bg-surface-2"
      )}
    >
      <span
        className={cn(
          "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-surface-1 shadow-sm transition-transform",
          checked && "translate-x-5"
        )}
      />
    </button>
  );
}
