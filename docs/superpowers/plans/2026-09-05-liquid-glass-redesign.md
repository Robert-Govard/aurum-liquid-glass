# Liquid Glass Redesign (этап 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ввести материал «Liquid Glass» (iOS-стиль: полупрозрачность + blur + верхний блик) в каркас приложения Aurum (Sidebar, Topbar, Dialog) и на Dashboard как пилотную страницу, попутно исправив найденный баг конфликта z-index между мобильным меню и диалогами.

**Architecture:** Один набор CSS-токенов (`--glass-*`, light/dark) в `index.css` + один переиспользуемый билдер классов `glassSurfaceClass()` в `components/ui/GlassSurface.tsx` — единственное место, определяющее «сколько стекла». Card получает необязательный `variant="glass"` (default остаётся `"solid"`, обратная совместимость для 11+ существующих мест использования на других страницах). Проект не имеет автотестов для фронтенда (только Playwright e2e для функциональных сценариев, без визуальных тестов) и на этой машине не установлен Node.js — верификация каждой задачи идёт через `docker run node:22-alpine` (typecheck/build) и ручную проверку в браузере через dev-сервер в контейнере; финальная задача дополнительно прогоняет полноценную сборку `docker compose build web`.

**Tech Stack:** React 19, Tailwind CSS v4 (`@tailwindcss/vite`), TypeScript, Docker (Node 22 Alpine образ для сборки/тайпчека — на хосте Node.js не установлен).

**Spec:** `docs/superpowers/specs/2026-09-05-liquid-glass-redesign-design.md`

## Global Constraints

- Не удалять существующие комментарии в коде — можно актуализировать, но не убирать (CLAUDE.md).
- Изменения атомарны по задачам/файлам: default `Card` variant остаётся `"solid"`, ни одна из 11+ существующих страниц с обычными карточками не меняется этой работой (CLAUDE.md + спецификация).
- Мобильная адаптация проверяется сразу по ходу, не откладывается (CLAUDE.md).
- Никаких новых автотестов под эту задачу — только ручная проверка в браузере (спецификация, YAGNI).
- Эффект «сдержанный»: единственное значение blur — `16px` (`--glass-blur`), без дополнительных, более тяжёлых слоёв эффекта (спецификация).
- Commit-сообщения — только суть изменения, без упоминания модели/сессии ассистента (CLAUDE.md).
- В коде и коммитах не должно быть чувствительных данных (CLAUDE.md) — не актуально для чистого CSS/UI, но не трогаем `.env`/секреты в рамках этой работы.
- На хосте нет `npm`/`node` — все команды сборки/тайпчека идут через Docker (`node:22-alpine`), не через голый `npm ...`.
- Работа выполняется в изолированном git worktree по пути `/Users/govard/Aurum/.claude/worktrees/liquid-glass-redesign` — все команды (включая `docker run -v "$(pwd)/frontend"...`) выполняются из этого каталога, не из основного чекаута `/Users/govard/Aurum`.

---

### Task 1: Design tokens материала стекла + установка зависимостей

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: CSS custom properties `--glass-bg`, `--glass-border`, `--glass-highlight`, `--glass-blur` (light + dark), проброшенные в `@theme` как `--color-glass-bg`, `--color-glass-border`, `--color-glass-highlight` → доступны как Tailwind-утилиты `bg-glass-bg`, `border-glass-border`, `bg-glass-highlight`, а `--glass-blur` — как raw CSS var для `backdrop-blur-[var(--glass-blur)]`.

- [x] **Step 1: Установить зависимости фронтенда (один раз для всего плана)**

Зависимости уже установлены при настройке worktree (`docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm install`, выполнено из корня worktree). `frontend/node_modules` уже в `.gitignore` — коммитить не нужно.

- [ ] **Step 2: Добавить токены в `:root` (светлая тема)**

В `frontend/src/index.css` найти блок:

```css
  --border: rgba(11, 11, 11, 0.1);
  --gridline: #e1e0d9;

  --success: #006300;
```

Заменить на:

```css
  --border: rgba(11, 11, 11, 0.1);
  --gridline: #e1e0d9;
  --glass-bg: rgba(252, 252, 251, 0.6);
  --glass-border: rgba(11, 11, 11, 0.08);
  --glass-highlight: rgba(255, 255, 255, 0.7);
  --glass-blur: 16px;

  --success: #006300;
```

- [ ] **Step 3: Добавить тёмные значения в `@media (prefers-color-scheme: dark)` блок**

Найти (обратите внимание на отступ в 4 пробела — это блок внутри `@media`):

```css
    --border: rgba(255, 255, 255, 0.1);
    --gridline: #2c2c2a;

    --success: #0ca30c;
```

Заменить на:

```css
    --border: rgba(255, 255, 255, 0.1);
    --gridline: #2c2c2a;
    --glass-bg: rgba(26, 26, 25, 0.55);
    --glass-border: rgba(255, 255, 255, 0.12);
    --glass-highlight: rgba(255, 255, 255, 0.16);

    --success: #0ca30c;
```

`--glass-blur` в тёмной теме не переопределяется — значение одинаковое для обеих тем, наследуется из `:root`.

- [ ] **Step 4: Добавить те же тёмные значения в явный `:root[data-theme="dark"]` блок**

Найти (отступ в 2 пробела — это отдельный блок ниже `@media`, а не тот же самый):

```css
  --border: rgba(255, 255, 255, 0.1);
  --gridline: #2c2c2a;

  --success: #0ca30c;
```

Заменить на:

```css
  --border: rgba(255, 255, 255, 0.1);
  --gridline: #2c2c2a;
  --glass-bg: rgba(26, 26, 25, 0.55);
  --glass-border: rgba(255, 255, 255, 0.12);
  --glass-highlight: rgba(255, 255, 255, 0.16);

  --success: #0ca30c;
```

- [ ] **Step 5: Прокинуть токены в `@theme`, чтобы получить Tailwind-утилиты**

Найти:

```css
  --color-border: var(--border);
  --color-gridline: var(--gridline);
  --color-success: var(--success);
```

Заменить на:

```css
  --color-border: var(--border);
  --color-gridline: var(--gridline);
  --color-glass-bg: var(--glass-bg);
  --color-glass-border: var(--glass-border);
  --color-glass-highlight: var(--glass-highlight);
  --color-success: var(--success);
```

- [ ] **Step 6: Проверить сборку**

CSS-синтаксис `tsc` не проверяет — гоняем полный `vite build`, который прогоняет Tailwind. Выполнять из корня worktree (`/Users/govard/Aurum/.claude/worktrees/liquid-glass-redesign`):

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run build
```

Expected: `vite build` завершается строкой вида `✓ built in ...s` и кодом выхода 0, без ошибок PostCSS/Tailwind.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/index.css
git commit -m "$(cat <<'EOF'
feat: добавить токены материала Liquid Glass в index.css
EOF
)"
```

---

### Task 2: Примитив `glassSurfaceClass`

**Files:**
- Create: `frontend/src/components/ui/GlassSurface.tsx`

**Interfaces:**
- Consumes: Tailwind-утилиты `bg-glass-bg`, `border-glass-border`, `bg-glass-highlight` и CSS-переменную `--glass-blur` из Task 1; `cn` из `@/lib/utils`.
- Produces: `glassSurfaceClass(className?: string): string` — единственная функция, собирающая классы материала стекла. Используется в Tasks 4–8 как `glassSurfaceClass("...другие классы...")`.

- [ ] **Step 1: Создать файл**

```tsx
import { cn } from "@/lib/utils";

/** Tailwind-классы материала Liquid Glass: полупрозрачная заливка, блюр
 * фона, тонкий светящийся край и 1px блик сверху (как будто на панель
 * падает свет). Экспортируется как билдер классов, а не только как
 * компонент-обёртка — часть потребителей (Sidebar-<aside>, Topbar-<header>,
 * Dialog-<div>) применяет материал прямо на свой семантический элемент, без
 * лишней обёртки. Единственное место, где меняется интенсивность эффекта —
 * значения самих токенов заданы в index.css (--glass-*). */
export function glassSurfaceClass(className?: string): string {
  return cn(
    "relative border border-glass-border bg-glass-bg backdrop-blur-[var(--glass-blur)]",
    "before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-glass-highlight before:content-['']",
    className
  );
}
```

- [ ] **Step 2: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: команда (`tsc -b --noEmit`) завершается без вывода ошибок, код выхода 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/GlassSurface.tsx
git commit -m "$(cat <<'EOF'
feat: добавить примитив glassSurfaceClass для материала Liquid Glass
EOF
)"
```

---

### Task 3: Амбиентная фоновая подложка

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: ничего нового (только существующие токены `series-1`, `series-4`, уже проброшенные в `@theme` до этой работы).

- [ ] **Step 1: Убрать сплошной фон у корневого контейнера и добавить декоративный слой**

Найти в `frontend/src/App.tsx`:

```tsx
  return (
    <div className="flex min-h-screen bg-surface-0">
      <Sidebar
```

Заменить на:

```tsx
  return (
    <div className="flex min-h-screen">
      {/* Амбиентная подложка, на которой «преломляется» стеклянный хром
          (Sidebar/Topbar/Dialog) — на плоском surface-0 полупрозрачные
          поверхности выглядели бы просто серыми. Fixed + отрицательный
          z-index: слой позади всего контента приложения, но поверх обычного
          фона <body> из index.css. Цвета — уже существующие токены (золото
          логотипа ~= series-4, один акцентный series-1), а не новые
          хардкод-значения. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -left-24 -top-24 h-96 w-96 rounded-full bg-series-4/10 blur-3xl" />
        <div className="absolute right-0 top-1/3 h-96 w-96 rounded-full bg-series-1/10 blur-3xl" />
      </div>
      <Sidebar
```

- [ ] **Step 2: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 3: Ручная визуальная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173` в браузере. Ожидается: едва заметные размытые золотистое и синее пятна по краям экрана вместо ровного однотонного фона; проверить в обеих темах (переключатель темы — Настройки, либо системная тёмная тема ОС). Данные с бэкенда не нужны для этой проверки — важна только фоновая подложка. Остановить контейнер (Ctrl+C) после проверки.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "$(cat <<'EOF'
feat: добавить амбиентную фоновую подложку под стеклянный интерфейс
EOF
)"
```

---

### Task 4: Sidebar → стекло

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `glassSurfaceClass` из `@/components/ui/GlassSurface` (Task 2).

- [ ] **Step 1: Импортировать `glassSurfaceClass`**

Добавить импорт рядом с остальными в `frontend/src/components/layout/Sidebar.tsx`:

```tsx
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
```

- [ ] **Step 2: Десктопная панель → стекло**

Найти:

```tsx
      <aside
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface-1 transition-[width] duration-150 lg:flex",
          collapsed ? "w-[72px]" : "w-56"
        )}
      >
```

Заменить на:

```tsx
      <aside
        className={glassSurfaceClass(
          cn(
            "sticky top-0 hidden h-screen shrink-0 flex-col transition-[width] duration-150 lg:flex",
            collapsed ? "w-[72px]" : "w-56"
          )
        )}
      >
```

- [ ] **Step 3: Мобильная шторка → стекло**

Найти:

```tsx
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-surface-1 shadow-xl">
```

Заменить на:

```tsx
          <aside className={glassSurfaceClass("absolute inset-y-0 left-0 flex w-64 flex-col shadow-xl")}>
```

- [ ] **Step 4: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 5: Ручная визуальная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173`. На широком окне (≥1024px) — десктопная боковая панель полупрозрачная, сквозь неё видна амбиентная подложка из Task 3. Сузить окно до мобильной ширины, открыть меню через иконку-гамбургер в шапке — шторка тоже стеклянная. Проверить в обеих темах. Остановить контейнер после проверки.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "$(cat <<'EOF'
feat: перевести Sidebar на материал Liquid Glass
EOF
)"
```

---

### Task 5: Topbar → стекло

**Files:**
- Modify: `frontend/src/components/layout/Topbar.tsx`

**Interfaces:**
- Consumes: `glassSurfaceClass` из `@/components/ui/GlassSurface` (Task 2).

- [ ] **Step 1: Импортировать `glassSurfaceClass` и заменить классы шапки**

Добавить импорт:

```tsx
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
```

Найти:

```tsx
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-surface-0/95 px-4 py-3.5 backdrop-blur sm:px-6 lg:px-8">
```

Заменить на:

```tsx
    <header className={glassSurfaceClass("sticky top-0 z-30 flex items-center gap-3 px-4 py-3.5 sm:px-6 lg:px-8")}>
```

- [ ] **Step 2: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 3: Ручная визуальная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173`, прокрутить страницу вниз — верхняя панель остаётся прилипшей (`sticky`) и стеклянной, под ней при прокрутке виден размытый контент. Проверить в обеих темах, на мобильной и десктопной ширине. Остановить контейнер после проверки.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/Topbar.tsx
git commit -m "$(cat <<'EOF'
feat: перевести Topbar на материал Liquid Glass
EOF
)"
```

---

### Task 6: Dialog → стекло + фикс z-index бага

**Files:**
- Modify: `frontend/src/components/ui/Dialog.tsx`

**Interfaces:**
- Consumes: `glassSurfaceClass` из `@/components/ui/GlassSurface` (Task 2).

- [ ] **Step 1: Импортировать `glassSurfaceClass`**

Добавить импорт рядом с остальными в `frontend/src/components/ui/Dialog.tsx`:

```tsx
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
```

- [ ] **Step 2: Поднять z-index оверлея и заменить материал листа**

Найти:

```tsx
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      )}
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-border bg-surface-1 p-5 shadow-xl sm:max-w-md sm:rounded-2xl"
        onClick={(event) => event.stopPropagation()}
      >
```

Заменить на:

```tsx
  return (
    <div
      className={cn(
        // z-[60]: должен перекрывать мобильную шторку Sidebar (z-50, см.
        // Sidebar.tsx) — иначе диалог, открытый при открытой шторке,
        // визуально оказывается под ней. Баг, найденный при аудите UI.
        "fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      )}
      onClick={onClose}
    >
      <div
        className={glassSurfaceClass("max-h-[90vh] w-full overflow-y-auto rounded-t-2xl p-5 shadow-xl sm:max-w-md sm:rounded-2xl")}
        onClick={(event) => event.stopPropagation()}
      >
```

- [ ] **Step 3: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 4: Ручная визуальная и функциональная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173/goals`, нажать «Add goal» (или аналогичную кнопку добавления) — диалог должен выглядеть стеклянным листом (снизу на мобильной ширине, по центру на десктопной). В DevTools → Elements проверить computed-стиль: внешний контейнер диалога (`div.fixed.inset-0`) имеет `z-index: 60`, а контейнер мобильной шторки Sidebar (`div.fixed.inset-0.z-50` из `Sidebar.tsx`, видно при открытом мобильном меню) — `z-index: 50`, то есть диалог гарантированно выше. Закрыть диалог по Escape и по клику на подложку — оба способа должны продолжать работать. Остановить контейнер после проверки.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Dialog.tsx
git commit -m "$(cat <<'EOF'
fix: диалоги теперь выше мобильной шторки навигации (z-index), Dialog переведён на Liquid Glass
EOF
)"
```

---

### Task 7: Button → лёгкое стеклянное hover-состояние

**Files:**
- Modify: `frontend/src/components/ui/Button.tsx`

**Interfaces:**
- Consumes: токены `--color-glass-bg`, `--glass-blur` из Task 1 (напрямую через Tailwind-утилиты, без `glassSurfaceClass` — эффект здесь легче: без рамки и блика).

- [ ] **Step 1: Обновить hover-классы secondary/ghost**

Найти:

```tsx
const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-text-primary text-surface-1 hover:opacity-90",
  secondary: "bg-surface-2 text-text-primary hover:bg-surface-2/70",
  ghost: "bg-transparent text-text-secondary hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90",
};
```

Заменить на:

```tsx
const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-text-primary text-surface-1 hover:opacity-90",
  // Лёгкий вариант Liquid Glass: без рамки и верхнего блика (это не
  // отдельная панель, а просто hover-состояние кнопки на чужом фоне) —
  // только полупрозрачность + блюр из тех же токенов --glass-*.
  secondary: "bg-surface-2 text-text-primary hover:bg-glass-bg hover:backdrop-blur-[var(--glass-blur)]",
  ghost: "bg-transparent text-text-secondary hover:bg-glass-bg hover:backdrop-blur-[var(--glass-blur)]",
  danger: "bg-danger text-white hover:opacity-90",
};
```

- [ ] **Step 2: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 3: Ручная визуальная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173/goals`, нажать «Add goal», навести курсор на кнопку «Отмена» (`variant="ghost"`) в диалоге — фон должен стать лёгким полупрозрачным блюром вместо прежней плоской заливки. Проверить в обеих темах. Остановить контейнер после проверки.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/Button.tsx
git commit -m "$(cat <<'EOF'
feat: лёгкое стеклянное hover-состояние для кнопок secondary/ghost
EOF
)"
```

---

### Task 8: Card `variant="glass"` + пилот на Dashboard (StatCard)

**Files:**
- Modify: `frontend/src/components/ui/Card.tsx`
- Modify: `frontend/src/components/dashboard/StatCard.tsx`

**Interfaces:**
- Consumes: `glassSurfaceClass` из `@/components/ui/GlassSurface` (Task 2).
- Produces: `Card` принимает необязательный проп `variant?: "solid" | "glass"` (default `"solid"`) — потребители на других страницах не меняются.

- [ ] **Step 1: Добавить `variant` в Card**

Заменить содержимое `frontend/src/components/ui/Card.tsx` целиком на:

```tsx
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";

type CardVariant = "solid" | "glass";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
}

export function Card({ className, variant = "solid", ...props }: CardProps) {
  return (
    <div
      className={
        variant === "glass"
          ? glassSurfaceClass(cn("min-w-0 rounded-xl shadow-sm", className))
          : cn("min-w-0 rounded-xl border border-border bg-surface-1 shadow-sm", className)
      }
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center justify-between gap-2 p-4 sm:p-5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-xs font-semibold uppercase tracking-wide text-text-muted", className)}
      {...props}
    />
  );
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 pt-0 sm:p-5 sm:pt-0", className)} {...props} />;
}
```

- [ ] **Step 2: Применить `variant="glass"` на Dashboard StatCard**

В `frontend/src/components/dashboard/StatCard.tsx` найти:

```tsx
    <Card className="p-4 sm:p-5">
```

Заменить на:

```tsx
    <Card variant="glass" className="p-4 sm:p-5">
```

- [ ] **Step 3: Проверить типы**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок.

- [ ] **Step 4: Ручная визуальная проверка**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app -p 5173:5173 node:22-alpine npm run dev -- --host 0.0.0.0
```

Открыть `http://localhost:5173/` (Dashboard). Без запущенного бэкенда карточки покажут placeholder-значения («…») — этого достаточно, чтобы оценить сам материал: 4 верхние карточки (StatCard) должны быть стеклянными (полупрозрачными, с блюром и лёгким бликом сверху), остальные карточки на странице (расходы по категориям, последние транзакции) — остаются обычными (`variant` по умолчанию `"solid"`), это ожидаемо и будет исправлено на следующих этапах. Проверить в обеих темах. Остановить контейнер после проверки.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Card.tsx frontend/src/components/dashboard/StatCard.tsx
git commit -m "$(cat <<'EOF'
feat: добавить Card variant="glass", применить на StatCard в Dashboard
EOF
)"
```

---

### Task 9: Версия, changelog и финальная проверка полной сборки

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `frontend/package.json`
- Create: `UPDATES.md`

**Interfaces:** нет — финальная задача, ничего не потребляют более поздние задачи.

- [ ] **Step 1: Поднять версию бэкенда**

В `backend/app/core/config.py` найти:

```python
APP_VERSION = "1.1.5"
```

Заменить на:

```python
APP_VERSION = "1.2.0"
```

- [ ] **Step 2: Поднять версию фронтенда**

В `frontend/package.json` найти:

```json
  "version": "1.1.5",
```

Заменить на:

```json
  "version": "1.2.0",
```

- [ ] **Step 3: Создать `UPDATES.md`**

Создать файл `UPDATES.md` в корне worktree (`/Users/govard/Aurum/.claude/worktrees/liquid-glass-redesign/UPDATES.md`) со следующим содержимым:

```markdown
# Обновления

## 2026-09-05 — v1.2.0

Редизайн интерфейса в стиле Liquid Glass (iOS), этап 1 — каркас приложения и Dashboard:

- Новая система токенов материала стекла (`--glass-*`) в `index.css`, для светлой и тёмной темы.
- Переиспользуемый примитив `glassSurfaceClass` — единая реализация материала (полупрозрачность, блюр, верхний блик).
- Sidebar, Topbar и Dialog переведены на стеклянный материал.
- У `Card` появился вариант `variant="glass"`, применён на StatCard (Dashboard) как пилотная страница.
- Кнопки (`secondary`/`ghost`) получили лёгкое стеклянное hover-состояние.
- Добавлена амбиентная фоновая подложка в каркасе приложения — декоративные размытые пятна, на которых видно преломление стекла.
- Исправлен баг: диалоговые окна и мобильная шторка навигации использовали одинаковый z-index (50) — диалог мог визуально оказаться под открытой шторкой; диалогам поднят z-index до 60.

Остальные страницы приложения переводятся на стекло в следующих этапах.
```

- [ ] **Step 4: Проверить типы затронутых файлов**

Из корня worktree:

```bash
docker run --rm -v "$(pwd)/frontend":/app -w /app node:22-alpine npm run lint
```

Expected: без ошибок (в этой задаче `.tsx`/`.ts` не менялись, но это финальная проверка перед полной сборкой).

- [ ] **Step 5: Полная сборка production-образа**

Из корня worktree:

```bash
docker compose build web
```

Expected: сборка `web` завершается успешно (стадии `build` → `npm run build`, затем `nginx`), без ошибок. Это более строгая проверка, чем `npm run lint`/`npm run build` в одиночном контейнере — использует реальный `Dockerfile` проекта.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py frontend/package.json UPDATES.md
git commit -m "$(cat <<'EOF'
chore: версия 1.2.0 — Liquid Glass редизайн, этап 1 (каркас + Dashboard)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Токены (`--glass-*`, light/dark) → Task 1. ✅
- Амбиентная подложка → Task 3. ✅
- Примитив `GlassSurface`/`glassSurfaceClass` → Task 2. ✅
- Sidebar, Topbar, Dialog → Tasks 4, 5, 6. ✅
- Card `variant="glass"` (default `"solid"`) → Task 8. ✅
- Button secondary/ghost hover → Task 7. ✅
- Dashboard/StatCard как пилот → Task 8. ✅
- Баг z-index Dialog vs мобильный Sidebar → Task 6. ✅
- Мобильная адаптация проверяется по ходу → в каждой ручной проверке (Tasks 3–8) явно указана проверка мобильной ширины. ✅
- Версия 1.1.5 → 1.2.0, UPDATES.md → Task 9. ✅
- Никаких новых автотестов (YAGNI) → везде используется ручная проверка + существующие `npm run lint`/`build`, новых test-файлов не создаётся. ✅

**Placeholder scan:** пройден — везде даны точные фрагменты кода и команды, без «TBD»/«добавить обработку ошибок»/т.п.

**Type consistency:** `glassSurfaceClass(className?: string): string` — сигнатура одинакова во всех местах использования (Tasks 4–6, 8); `Card` проп `variant?: "solid" | "glass"` заведён в Task 8 и нигде больше не переопределяется иначе.

---

Plan complete and saved to `docs/superpowers/plans/2026-09-05-liquid-glass-redesign.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
