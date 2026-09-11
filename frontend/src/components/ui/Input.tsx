import type { InputHTMLAttributes, LabelHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface-1 px-3 text-sm text-text-primary outline-none focus:border-series-1",
        className
      )}
      {...props}
    />
  );
}

// Select живёт отдельно в components/ui/Select.tsx — это не тонкая
// обёртка вроде Input/Label, а полноценный компонент с собственным
// состоянием (показывает варианты в панели снизу вместо нативного
// <select>, который на Android WebView открывался как системное меню
// поверх приложения, найдено на реальном устройстве).

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1 block text-xs font-medium text-text-secondary", className)} {...props} />;
}
