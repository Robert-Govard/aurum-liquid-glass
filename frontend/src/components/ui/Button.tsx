import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-text-primary text-surface-1 hover:opacity-90",
  secondary: "bg-surface-2 text-text-primary hover:bg-surface-2/70",
  ghost: "bg-transparent text-text-secondary hover:bg-surface-2",
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
