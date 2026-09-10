import { LogOut, Menu } from "lucide-react";
import { useLocation } from "react-router-dom";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { logout, useAuthState } from "@/lib/auth";

interface TopbarProps {
  onOpenMobileNav: () => void;
}

export function Topbar({ onOpenMobileNav }: TopbarProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { user } = useAuthState();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className={glassSurfaceClass("sticky top-0 z-30 flex items-center gap-3 border-b border-glass-border px-4 py-3.5 sm:px-6 lg:px-8")}>
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label={t("topbar.openMenu")}
        className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2 lg:hidden"
      >
        <Menu size={20} />
      </button>
      <h1 className="text-lg font-semibold text-text-primary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</h1>
      {user && (
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* Hidden below sm: the header is already tight on a phone
              screen with the hamburger button and page title, and the
              logout icon alone is enough to act on there — the email is a
              nice-to-have identity check, not something a mobile user
              needs visible at all times. */}
          <span className="hidden truncate text-xs text-text-muted sm:inline" title={user.email}>
            {user.email}
          </span>
          <button
            type="button"
            onClick={() => void logout()}
            aria-label={t("topbar.logout")}
            title={t("topbar.logout")}
            className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2"
          >
            <LogOut size={18} />
          </button>
        </div>
      )}
    </header>
  );
}
