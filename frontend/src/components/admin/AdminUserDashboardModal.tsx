import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { useAdminUserDashboard } from "@/hooks/useAdmin";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

interface AdminUserDashboardModalProps {
  user: AdminUser | null;
  onClose: () => void;
}

/** Share of income left over after spending — same formula as
 * DashboardPage's own savingsRate(); duplicated rather than imported
 * since DashboardPage doesn't export it and it's a 2-line pure function. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

/** Read-only dashboard popup for one user, opened from AdminUserList.
 * Always mounted in AdminPage (never conditionally rendered based on
 * whether a user is selected) — Dialog's own close animation keeps ITSELF
 * mounted for a short timeout after `open` goes false, but that only
 * works if this wrapper component doesn't get removed from the tree
 * first. */
export function AdminUserDashboardModal({ user, onClose }: AdminUserDashboardModalProps) {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  // Keeps showing the last-viewed user's data while Dialog's close
  // animation plays (during which `user` has already gone back to null).
  const [displayUser, setDisplayUser] = useState<AdminUser | null>(user);
  useEffect(() => {
    if (user) setDisplayUser(user);
  }, [user]);

  const registrationYear = displayUser ? new Date(displayUser.created_at).getFullYear() : now.getFullYear();
  const years: number[] = [];
  for (let y = now.getFullYear(); y >= registrationYear; y--) years.push(y);

  const { data, isLoading, isError } = useAdminUserDashboard(displayUser?.id ?? null, year, month);
  const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;
  const currency = displayUser?.currency;

  return (
    <Dialog open={user !== null} onClose={onClose} title={displayUser?.email ?? ""}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <MonthSelector month={month} onChange={setMonth} />
          </div>
          <YearSelector years={years} year={year} onChange={setYear} />
        </div>

        {isError ? (
          <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {t("admin.loadError")}
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label={t("dashboard.statRealIncomeLabel")}
              value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0, currency)}
              caption={t("dashboard.statRealIncomeCaption")}
              tone="success"
            />
            <StatCard
              label={t("dashboard.statSpentLabel")}
              value={isLoading ? "…" : formatCurrency(data?.spent ?? 0, currency)}
              caption={t("dashboard.statSpentCaption")}
              tone="danger"
            />
            <StatCard
              label={t("dashboard.statNetLabel")}
              value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0, currency)}
              caption={t("dashboard.statNetCaption")}
              tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
            />
            <StatCard
              label={t("dashboard.statSavingsRateLabel")}
              value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
              caption={t("dashboard.statSavingsRateCaption")}
              tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
            />
          </div>
        )}
      </div>
    </Dialog>
  );
}
