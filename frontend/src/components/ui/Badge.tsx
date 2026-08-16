import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-text-secondary",
        className
      )}
      {...props}
    />
  );
}
