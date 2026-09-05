import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-text-primary text-surface-1 hover:opacity-90",
  // Лёгкий вариант Liquid Glass: без рамки и верхнего блика (это не
  // отдельная панель, а просто hover-состояние кнопки на чужом фоне) —
  // только полупрозрачность + блюр из тех же токенов --glass-*.
  secondary: "bg-surface-2 text-text-primary hover:bg-glass-bg hover:backdrop-blur-[var(--glass-blur)]",
  ghost: "bg-transparent text-text-secondary hover:bg-glass-bg hover:backdrop-blur-[var(--glass-blur)]",
  danger: "bg-danger text-white hover:opacity-90",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        VARIANT_CLASSES[variant],
        className
      )}
      {...props}
    />
  );
}
