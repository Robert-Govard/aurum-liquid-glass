import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-text-primary text-surface-1 hover:opacity-90",
  // Лёгкий вариант Liquid Glass: видимая заливка при hover (как и раньше)
  // плюс блюр из токенов --glass-* поверх неё — сам --glass-bg слишком
  // прозрачен, чтобы быть заметным сам по себе (найдено финальным ревью).
  secondary: "bg-surface-2 text-text-primary hover:bg-surface-2/70 hover:backdrop-blur-[var(--glass-blur)]",
  ghost: "bg-transparent text-text-secondary hover:bg-surface-2 hover:backdrop-blur-[var(--glass-blur)]",
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
