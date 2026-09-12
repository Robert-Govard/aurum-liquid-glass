import { NavLink } from "react-router-dom";
import { Lock, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";

interface NavListProps {
  collapsed: boolean;
}

function NavList({ collapsed }: NavListProps) {
  const { t } = useTranslation();
  const { user } = useAuthState();
  const items = NAV_ITEMS.filter((item) => !item.adminOnly || user?.is_admin);

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-2">
      {items.map((item) => {
        const Icon = item.icon;
        const label = t(item.labelKey);
        if (item.disabled) {
          return (
            <span
              key={item.to}
              title={collapsed ? `${label} (${t("nav.comingSoon")})` : undefined}
              className={cn(
                "flex cursor-not-allowed items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted",
                collapsed && "justify-center px-0"
              )}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && (
                <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                  <span className="truncate">{label}</span>
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none">
                    {t("nav.comingSoon")}
                  </span>
                </span>
              )}
            </span>
          );
        }

        const locked = item.premiumOnly && !user?.is_premium;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-2 hover:text-text-primary",
                collapsed && "justify-center px-0",
                isActive && "bg-surface-2 text-text-primary"
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && (
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span className="truncate">{label}</span>
                {locked && <Lock size={12} className="shrink-0 text-text-muted" aria-label={t("nav.premiumBadge")} />}
              </span>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

/** Desktop-only (`lg:flex`) постоянная боковая панель, схлопывается между
 * иконками-only и полной шириной (collapsible between icon-only and full
 * width). Мобильная off-canvas версия этого компонента убрана — на <lg
 * навигация теперь MobileTabBar (см. App.tsx). */
export function Sidebar({ collapsed, onToggleCollapsed }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside
      className={glassSurfaceClass(
        cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-glass-border transition-[width] duration-150 lg:flex",
          collapsed ? "w-[72px]" : "w-56"
        )
      )}
    >
      {collapsed ? (
        // Collapsed: the logo doubles as an "expand" button — the sidebar
        // has no visible label to click in this state, so the icon itself
        // needs to be the way back to the full menu.
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={t("sidebar.expandMenu")}
          className="flex items-center justify-center gap-2 px-0 py-4 hover:opacity-80"
        >
          <Logo size={24} />
        </button>
      ) : (
        <div className="flex items-center gap-2 px-4 py-4">
          <Logo size={24} />
          <span className="text-lg font-semibold tracking-tight text-text-primary">Moneta</span>
        </div>
      )}
      <NavList collapsed={collapsed} />
      <div className="border-t border-border p-2.5">
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={collapsed ? t("sidebar.expandMenu") : t("sidebar.collapseMenu")}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted hover:bg-surface-2 hover:text-text-primary",
            collapsed && "justify-center px-0"
          )}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          {!collapsed && <span>{t("sidebar.collapse")}</span>}
        </button>
      </div>
    </aside>
  );
}
