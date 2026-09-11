import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Dialog } from "@/components/ui/Dialog";
import { GroupedList, GroupedListItem } from "@/components/ui/GroupedList";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { useTranslation } from "@/lib/i18n";
import { MOBILE_TAB_PATHS, NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const TAB_ITEMS = MOBILE_TAB_PATHS.map((path) => NAV_ITEMS.find((item) => item.to === path)!);
const MORE_ITEMS = NAV_ITEMS.filter((item) => !MOBILE_TAB_PATHS.includes(item.to));

function isItemActive(pathname: string, to: string): boolean {
  return to === "/" ? pathname === "/" : pathname.startsWith(to);
}

/** Нижний таб-бар — мобильная навигация (<lg), заменяет собой прежнее
 * гамбургер-меню + выезжающую шторку (см. Sidebar.tsx/Topbar.tsx). 4
 * самых частых раздела видны напрямую, остальные NAV_ITEMS — через
 * вкладку "Ещё", которая открывает GroupedList в Dialog-шторке снизу. */
export function MobileTabBar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);

  const isMoreActive = MORE_ITEMS.some((item) => isItemActive(location.pathname, item.to));

  return (
    <>
      <nav
        aria-label="Основная навигация"
        className={glassSurfaceClass(
          "fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t border-glass-border pb-[var(--safe-area-bottom)] lg:hidden"
        )}
      >
        {TAB_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(location.pathname, item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
                active ? "text-text-primary" : "text-text-muted"
              )}
            >
              <Icon size={22} />
              <span>{t(item.labelKey)}</span>
            </NavLink>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          className={cn(
            "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
            isMoreActive ? "text-text-primary" : "text-text-muted"
          )}
        >
          <MoreHorizontal size={22} />
          <span>{t("nav.more")}</span>
        </button>
      </nav>

      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={t("nav.more")}>
        <GroupedList>
          {MORE_ITEMS.map((item) => {
            const Icon = item.icon;
            if (item.disabled) {
              return (
                <GroupedListItem
                  key={item.to}
                  icon={Icon}
                  label={t(item.labelKey)}
                  disabled
                  trailing={<span className="text-[10px] text-text-muted">{t("nav.comingSoon")}</span>}
                />
              );
            }
            return (
              <GroupedListItem
                key={item.to}
                icon={Icon}
                label={t(item.labelKey)}
                onClick={() => {
                  navigate(item.to);
                  setMoreOpen(false);
                }}
              />
            );
          })}
        </GroupedList>
      </Dialog>
    </>
  );
}
