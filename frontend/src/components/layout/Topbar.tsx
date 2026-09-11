import { LogOut } from "lucide-react";
import { useLocation } from "react-router-dom";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";
import { glassSurfaceClass } from "@/components/ui/GlassSurface";
import { logout, useAuthState } from "@/lib/auth";

export function Topbar() {
  const location = useLocation();
  const { t } = useTranslation();
  const { user, accessToken } = useAuthState();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className={glassSurfaceClass("sticky top-0 z-30 flex items-center gap-3 border-b border-glass-border px-4 py-3.5 sm:px-6 lg:px-8")}>
      <h1 className="text-lg font-semibold text-text-primary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</h1>
      {accessToken && (
        // Gated on accessToken (not user) — login()/register() in auth.ts
        // set the access token BEFORE /auth/me resolves, so LoginGate
        // (which only checks accessToken) can already be showing the app
        // while `user` is still null. Gating this container on `user`
        // would hide the logout button entirely until a reload in that
        // window; gating on accessToken keeps it available as soon as
        // there's a session to log out of, while the email itself still
        // waits for `user` to actually be populated.
        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* Hidden below sm: the header is already tight on a phone
              screen with the page title, and the logout icon alone is
              enough to act on there — the email is a nice-to-have
              identity check, not something a mobile user needs visible
              at all times. */}
          {user && (
            <span className="hidden truncate text-xs text-text-muted sm:inline" title={user.email}>
              {user.email}
            </span>
          )}
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
