# iOS-стиль мобильного интерфейса — дизайн

**Дата:** 2026-09-11
**Статус:** на утверждение

## Контекст и цель

Aurum — веб-приложение (React + Tailwind v4, shadcn-подобные компоненты
собственной разработки) с уже существующей мобильной адаптацией и
недавно добавленной Android-обёрткой через Capacitor
(`docs/superpowers/plans/2026-09-10-android-capacitor-app.md`). Пользователь
попросил переделать интерфейс "как на айфоне" — навигация, внешний вид
компонентов и жесты должны заимствовать конвенции iOS, сохраняя текущую
золотую/тёмную тему Aurum ("Liquid Glass").

Изменения затрагивают **только мобильную ширину экрана** (`<lg`, т.е.
`<1024px` — порог, уже используемый в `Sidebar.tsx`/`Topbar.tsx` для
переключения между десктопным и мобильным layout) — это касается и
мобильного браузера, и Android-приложения одинаково, поскольку оба
рендерят один и тот же React-код на одной и той же ширине экрана.
Десктопная версия (`≥lg`) не меняется вообще.

## Global Constraints

- Ничего не менять в десктопной раскладке (`≥lg`) — только `<lg`.
- Тема Aurum (золото/тёмный, токены `--color-*` в `src/index.css`,
  Liquid Glass через `glassSurfaceClass`) остаётся неизменной — новые
  компоненты используют существующие токены, не вводят новых цветов.
  Про синий акцент/типографику Apple речи не идёт — только форма
  компонентов и паттерны навигации.
- Каждая строка текста — через `lib/i18n.ts` (`ru`/`en`, оба блока
  синхронно) — как и во всём остальном проекте.
- Нет доступа к браузеру/устройству для визуальной проверки — как и в
  предыдущих этапах, проверка ограничена сборкой TypeScript
  (`npm run build`) и вычитыванием кода; открыть и попробовать вживую
  на телефоне/в браузере нужно самостоятельно.
- Не трогать бэкенд — изменения полностью в `frontend/`.

## Архитектура

### 1. Навигация: нижний таб-бар + экран "Ещё"

Сейчас на `<lg` навигация — гамбургер-кнопка в `Topbar.tsx`, открывающая
выезжающую шторку `Sidebar.tsx` (off-canvas drawer с полным списком
`NAV_ITEMS`). Это заменяется на:

- **`MobileTabBar`** (новый компонент, `components/layout/MobileTabBar.tsx`)
  — фиксированная панель снизу экрана, видима только на `<lg`
  (`lg:hidden`), 5 вкладок: **Дашборд, Транзакции, Бюджет, Счета, Ещё**.
- **`MoreSheet`** — всплывающая снизу панель (переиспользует существующий
  `Dialog` из `components/ui/Dialog.tsx`, который уже открывается как
  bottom-sheet на `<sm`, см. ниже) со списком оставшихся 10 разделов в
  виде сгруппированного списка (см. `GroupedList` ниже): Капитал, Крипта,
  ROI, Категории, Cash Flow, Отчёты, Регулярные, Цели, Советы, Настройки.
- Гамбургер-кнопка в `Topbar.tsx` и мобильная off-canvas ветка
  `Sidebar.tsx` — удаляются. Десктопная (persistent rail) часть
  `Sidebar.tsx` не трогается.

**`lib/navigation.ts`** — добавляется список ключей для таб-бара, порядок
важен (порядок отображения вкладок):

```ts
export const MOBILE_TAB_PATHS: string[] = ["/", "/transactions", "/budget", "/accounts"];
```

`MobileTabBar` строит свои 4 основные вкладки фильтрацией `NAV_ITEMS` по
`MOBILE_TAB_PATHS` (в порядке `MOBILE_TAB_PATHS`, не порядке `NAV_ITEMS`),
плюс статичная 5-я вкладка "Ещё" (иконка `MoreHorizontal` из
`lucide-react`, ключ перевода `nav.more`). `MoreSheet` рендерит
`NAV_ITEMS.filter(item => !MOBILE_TAB_PATHS.includes(item.to))` — то есть
источник правды по-прежнему один (`NAV_ITEMS`), `MOBILE_TAB_PATHS` только
переупорядочивает/выделяет подмножество.

Определение активной вкладки — та же логика, что уже используется в
`Topbar.tsx`: `item.to === "/" ? pathname === "/" : pathname.startsWith(item.to)`.
Вкладка "Ещё" подсвечивается активной, когда текущий путь не совпадает ни
с одним из `MOBILE_TAB_PATHS` (то есть открыт один из разделов внутри
"Ещё").

`item.disabled` (существующее поле `NavItem`, сейчas ни на одном пункте
не выставлено, но зарезервировано) в `MoreSheet` рендерится так же, как
сегодня в `Sidebar.tsx` — некликабельная строка с бейджем "скоро".

### 2. Safe-area (отступы под системные элементы Android)

`index.html` уже содержит `viewport-fit=cover`, но `env(safe-area-inset-*)`
нигде не используется. В `src/index.css` (рядом с `@theme`/`:root`, где
объявлены остальные CSS-токены) добавляются:

```css
:root {
  --safe-area-top: env(safe-area-inset-top, 0px);
  --safe-area-bottom: env(safe-area-inset-bottom, 0px);
}
```

Применение:
- `MobileTabBar`: `padding-bottom: var(--safe-area-bottom)` (высота самой
  панели с иконками фиксированная, отступ — сверх неё), чтобы панель не
  перекрывалась системной полосой жестов Android.
- Контентная область `<main>` в `App.tsx`: на `<lg` дополнительный нижний
  padding, равный высоте таб-бара плюс `--safe-area-bottom`, чтобы
  последний элемент любого списка не прятался под фиксированной панелью.
  Реализуется через Tailwind arbitrary value:
  `pb-[calc(4.5rem+var(--safe-area-bottom))] lg:pb-6` (4.5rem — высота
  таб-бара с запасом; точное число implementer подбирает по фактической
  высоте `MobileTabBar`).

В браузере без вырезов/жестовой полосы `env()` возвращает 0px — отступы
безопасно вырождаются в обычные значения, поведение не меняется.

### 3. Внешний вид компонентов

- **`GroupedList` / `GroupedListItem`** (новые, `components/ui/GroupedList.tsx`)
  — сгруппированная карточка-список в стиле iOS Settings: закруглённая
  карточка (`glassSurfaceClass` + `rounded-xl`), строки разделены
  `divide-y divide-border`, у каждой строки иконка слева, текст, опционально
  `trailing` справа (по умолчанию `ChevronRight` из `lucide-react` для
  кликабельных строк). Используется в `MoreSheet`.
  **Не применяется на `SettingsPage`**: та страница собрана из
  специализированных карточек (`PreferencesCard` с парой `PillSelector`
  рядом, `CurrencyCard`, `AlertThresholdsCard` с числовыми полями,
  `BackupCard` с экспортом/импортом) — это не список "нажми → перейди",
  и упаковка их в `GroupedList` только ухудшила бы вёрстку без реальной
  пользы. Решение принято на этапе детального планирования, после
  прочтения содержимого этих карточек.
- **`Switch`** (новый, `components/ui/Switch.tsx`) — iOS-переключатель:
  трек `w-11 h-6 rounded-full`, цвет `bg-surface-2` (выкл) /
  `bg-text-primary` (вкл, тот же токен, что и `Button` variant="primary" —
  без новых цветов), белый кружок-бегунок, переезжающий через
  `translate-x` с `transition-transform`. API: `{ checked: boolean; onChange:
  (checked: boolean) => void; "aria-label": string }`. Заменяет
  единственный `<input type="checkbox">` в `AccountsPage.tsx` (чекбокс
  "показывать архивные").
- **`PillSelector`** (`components/layout/PillSelector.tsx`) — визуальное
  обновление под iOS segmented control: активный пункт получает
  скользящий фон (`layout`-анимация через CSS `transition` на
  `translateX`/ширину активного сегмента, без новых зависимостей — чистый
  CSS, без Framer Motion). Публичный API (`options`/`value`/`onChange`) не
  меняется — потребители (`MonthSelector`, `YearSelector`, `RangeSelector`,
  где бы они его ни использовали) не трогаются.
- **`Dialog.tsx`** — добавляется декоративный "хваталка"-индикатор
  (короткая закруглённая полоска сверху панели, `mx-auto h-1 w-9
  rounded-full bg-border`), видимый только в bottom-sheet режиме
  (`sm:hidden`, тем же брейкпоинтом, что уже разделяет bottom-sheet и
  центрированный modal в этом компоненте). Жест смахивания вниз для
  закрытия — **не добавляется** (вне запрошенного скоупа).
- Скругления: `Button` (`rounded-lg` → `rounded-xl`) и `Card`
  (`rounded-xl` → `rounded-2xl`, оба варианта — `solid` и `glass`) — на
  один шаг больше текущего каждый, ближе к iOS continuous corner radius
  и заодно к скруглению, которое уже использует bottom-sheet `Dialog`
  (`rounded-t-2xl`). Не вводить новый токен радиуса — использовать
  существующую шкалу Tailwind.

### 4. Жест: свайп назад с края экрана

Новый хук `hooks/useEdgeSwipeBack.ts`:

```ts
import { useEffect, useRef } from "react";
import { useNavigate, useNavigationType } from "react-router-dom";

const EDGE_ZONE_PX = 24;
const SWIPE_THRESHOLD_PX = 80;

/** Свайп от левого края экрана — переход на предыдущую страницу внутри
 * приложения, как в iOS. Считает "глубину" истории сам (react-router не
 * даёт это напрямую): PUSH увеличивает счётчик, POP уменьшает, REPLACE не
 * влияет. Жест игнорируется, если возвращаться внутри приложения некуда —
 * иначе на Android свайп у самого края экрана мог бы неожиданно закрыть
 * приложение через системный жест "назад".
 */
export function useEdgeSwipeBack(enabled: boolean): void {
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const depthRef = useRef(0);

  useEffect(() => {
    if (navigationType === "PUSH") depthRef.current += 1;
    else if (navigationType === "POP") depthRef.current = Math.max(0, depthRef.current - 1);
  }, [navigationType]);

  useEffect(() => {
    if (!enabled) return;
    let tracking = false;
    let startX = 0;
    let startY = 0;

    function onTouchStart(event: TouchEvent) {
      const touch = event.touches[0];
      if (!touch || touch.clientX > EDGE_ZONE_PX || depthRef.current <= 0) return;
      tracking = true;
      startX = touch.clientX;
      startY = touch.clientY;
    }

    function onTouchEnd(event: TouchEvent) {
      if (!tracking) return;
      tracking = false;
      const touch = event.changedTouches[0];
      if (!touch) return;
      const dx = touch.clientX - startX;
      const dy = Math.abs(touch.clientY - startY);
      if (dx > SWIPE_THRESHOLD_PX && dy < dx) navigate(-1);
    }

    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchend", onTouchEnd);
    };
  }, [enabled, navigate]);
}
```

`enabled` приходит из нового `hooks/useIsMobileViewport.ts` — в кодовой
базе пока нет ни одного хука на `matchMedia`, поэтому создаётся с нуля:

```ts
import { useEffect, useState } from "react";

const MOBILE_QUERY = "(max-width: 1023.98px)"; // синхронизировано с порогом `lg` (1024px) в Sidebar.tsx/Topbar.tsx

export function useIsMobileViewport(): boolean {
  const [isMobile, setIsMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setIsMobile(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
```

Подключается в `App.tsx`: `useEdgeSwipeBack(useIsMobileViewport())`.

Жест работает одинаково в мобильном браузере и в Android-приложении —
обычные `touch*`-события DOM, нативный Capacitor-плагин не требуется.

## Изменяемые/новые файлы

- Новые: `components/layout/MobileTabBar.tsx`, `components/ui/GroupedList.tsx`,
  `components/ui/Switch.tsx`, `hooks/useEdgeSwipeBack.ts`,
  `hooks/useIsMobileViewport.ts`.
- Изменяются: `lib/navigation.ts` (добавить `MOBILE_TAB_PATHS`),
  `App.tsx` (убрать `mobileNavOpen`, подключить `MobileTabBar` и
  `useEdgeSwipeBack`, добавить нижний padding контента),
  `components/layout/Sidebar.tsx` (убрать off-canvas ветку),
  `components/layout/Topbar.tsx` (убрать гамбургер/`onOpenMobileNav`),
  `components/layout/PillSelector.tsx` (визуал),
  `components/ui/Dialog.tsx` (drag handle),
  `components/ui/Button.tsx` (скругление),
  `components/ui/Card.tsx` (скругление, если применимо),
  `pages/AccountsPage.tsx` (использовать `Switch` вместо `<input type="checkbox">`),
  `src/index.css` (safe-area токены),
  `lib/i18n.ts` (новые ключи: `nav.more`, что-то для заголовка `MoreSheet`
  — например `nav.moreTitle`).

## Тестирование

Бэкенда изменения не касаются — тестирование ограничено фронтендом:

- `npm run build` (TypeScript + vite) после каждой значимой группы
  изменений — единственная автоматическая проверка, доступная в этой
  среде.
- Код-ревью на соответствие описанным здесь API и поведению (активная
  вкладка, фильтрация `NAV_ITEMS`, глубина истории для жеста, деградация
  `env()` до 0px).
- Явно зафиксировать в отчёте, что визуальный результат (реально ли
  вкладки видны, не наезжает ли контент на таб-бар, работает ли жест
  пальцем) не проверялся вживую — ни в браузере, ни на Android-устройстве.

## Вне скоупа (явно)

- Свайп-удаление строк в списках (транзакции и т.д.).
- Pull-to-refresh.
- Замена золотого акцента на системный синий iOS / шрифты Apple.
- Свайп-вниз для закрытия bottom-sheet `Dialog`.
- Любые изменения десктопной раскладки.
