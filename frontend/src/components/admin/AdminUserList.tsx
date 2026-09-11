import { Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/Switch";
import { formatCurrency, formatFullDate, pluralizeRu } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
import type { AdminUser } from "@/types";

interface AdminUserListProps {
  items: AdminUser[];
  currentUserId: number | undefined;
  onView: (user: AdminUser) => void;
  onToggleActive: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
}

function accountsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "счёт", "счёта", "счетов");
  return count === 1 ? "account" : "accounts";
}

function transactionsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "транзакция", "транзакции", "транзакций");
  return count === 1 ? "transaction" : "transactions";
}

export function AdminUserList({ items, currentUserId, onView, onToggleActive, onDelete }: AdminUserListProps) {
  const { t, language } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("admin.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((user) => {
        const isSelf = user.id === currentUserId;
        return (
          <li key={user.id} className={`flex flex-wrap items-center gap-3 py-3 ${!user.is_active ? "opacity-50" : ""}`}>
            <button type="button" onClick={() => onView(user)} className="min-w-0 flex-1 text-left">
              <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-text-primary">
                <span className="min-w-0 truncate">{user.email}</span>
                {user.is_admin && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("admin.adminBadge")}
                  </span>
                )}
                {!user.is_active && (
                  <span className="shrink-0 rounded bg-danger/10 px-1 py-0.5 text-[10px] leading-none text-danger">
                    {t("admin.disabledBadge")}
                  </span>
                )}
              </span>
              <span className="block text-xs text-text-muted">
                {t("admin.registeredOn", { date: formatFullDate(user.created_at) })}
                {" · "}
                {user.last_login_at
                  ? t("admin.lastLoginOn", { date: formatFullDate(user.last_login_at) })
                  : t("admin.neverLoggedIn")}
              </span>
              <span className="block text-xs text-text-muted">
                {user.accounts_count} {accountsCountLabel(user.accounts_count, language)}
                {", "}
                {user.transactions_count} {transactionsCountLabel(user.transactions_count, language)}
                {" · "}
                {t("admin.netWorthLabel", { amount: formatCurrency(user.net_worth, user.currency) })}
              </span>
            </button>
            {!isSelf && (
              <span className="flex shrink-0 items-center gap-3">
                <Switch
                  checked={user.is_active}
                  onChange={() => onToggleActive(user)}
                  aria-label={user.is_active ? t("admin.disable") : t("admin.enable")}
                />
                <button
                  type="button"
                  onClick={() => onDelete(user)}
                  aria-label={t("common.delete")}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={16} />
                </button>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
