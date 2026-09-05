import { cn } from "@/lib/utils";

/** Tailwind-классы материала Liquid Glass: полупрозрачная заливка, блюр
 * фона и 1px блик сверху (как будто на панель падает свет). Рамка
 * намеренно НЕ входит в базовый набор — у разных потребителей она разная
 * по сторонам (Topbar — только снизу, Sidebar — только справа, Card и
 * Dialog — со всех сторон), поэтому каждый вызывающий указывает свою
 * рамку явно через className. Экспортируется как билдер классов, а не
 * только как компонент-обёртка — часть потребителей (Sidebar-<aside>,
 * Topbar-<header>, Dialog-<div>) применяет материал прямо на свой
 * семантический элемент, без лишней обёртки. Единственное место, где
 * меняется интенсивность эффекта — значения самих токенов заданы в
 * index.css (--glass-*). */
export function glassSurfaceClass(className?: string): string {
  return cn(
    "relative bg-glass-bg backdrop-blur-[var(--glass-blur)]",
    "before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-glass-highlight before:content-['']",
    className
  );
}
