import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useUpdateAdminUserPremium } from "@/hooks/useAdmin";
import { formatFullDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

const FOREVER_YEARS = 100;

interface AdminPremiumModalProps {
  user: AdminUser | null;
  onClose: () => void;
}

/** Opened from AdminUserList's per-row "manage subscription" button.
 * Permanently mounted (like AdminUserDashboardModal) with a displayUser
 * that lags one render behind `user` becoming null, so Dialog's own
 * close-fade animation has a real user object to render text about
 * while it plays — see Dialog.tsx's contract. */
export function AdminPremiumModal({ user, onClose }: AdminPremiumModalProps) {
  const { t } = useTranslation();
  const updatePremium = useUpdateAdminUserPremium();
  const [displayUser, setDisplayUser] = useState<AdminUser | null>(null);
  const [date, setDate] = useState("");

  useEffect(() => {
    if (user) {
      setDisplayUser(user);
      setDate("");
    }
  }, [user]);

  function grantUntil(iso: string) {
    if (!displayUser) return;
    updatePremium.mutate({ id: displayUser.id, premiumUntil: iso }, { onSuccess: onClose });
  }

  function grantForever() {
    const forever = new Date();
    forever.setFullYear(forever.getFullYear() + FOREVER_YEARS);
    grantUntil(forever.toISOString());
  }

  function revoke() {
    if (!displayUser) return;
    updatePremium.mutate({ id: displayUser.id, premiumUntil: null }, { onSuccess: onClose });
  }

  return (
    <Dialog open={user !== null} onClose={onClose} title={t("admin.premiumModalTitle")}>
      {displayUser && (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            {displayUser.is_premium && displayUser.premium_until
              ? t("admin.premiumActiveUntil", { date: formatFullDate(displayUser.premium_until) })
              : t("admin.premiumInactive")}
          </p>
          <div>
            <Label htmlFor="premium-until-date">{t("admin.premiumUntilLabel")}</Label>
            <Input id="premium-until-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={!date || updatePremium.isPending}
              onClick={() => grantUntil(new Date(date).toISOString())}
            >
              {t("admin.premiumGrantUntil")}
            </Button>
            <Button type="button" variant="secondary" disabled={updatePremium.isPending} onClick={grantForever}>
              {t("admin.premiumGrantForever")}
            </Button>
            {displayUser.is_premium && (
              <Button type="button" variant="secondary" disabled={updatePremium.isPending} onClick={revoke}>
                {t("admin.premiumRevoke")}
              </Button>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}
