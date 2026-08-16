import { ArrowLeftRight, Pencil, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction } from "@/types";

interface TransactionsTableProps {
  items: Transaction[];
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
}

export function TransactionsTable({ items, onEdit, onDelete }: TransactionsTableProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-12 text-center text-sm text-text-muted">{t("transactions.noneFound")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((tx) => {
        const isTransfer = tx.type === "transfer";
        const isExpense = tx.type === "expense";
        const Icon = isTransfer ? ArrowLeftRight : getCategoryIcon(tx.category?.icon);
        const color = isTransfer ? "var(--text-muted)" : tx.category?.color ?? "var(--text-muted)";

        return (
          <li key={tx.id} className="group flex items-center gap-3 py-3">
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
              style={{ backgroundColor: typeof color === "string" && color.startsWith("#") ? `${color}26` : "var(--surface-2)" }}
            >
              <Icon size={16} style={{ color }} />
            </span>

            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text-primary">{tx.description}</span>
              <span className="block truncate text-xs text-text-muted">
                {formatTransactionDate(tx.date)} · {tx.account.name}
                {isTransfer && tx.transfer_account_id ? ` ${t("transactions.transferSuffix")}` : ""}
                {tx.category ? ` · ${translateCategoryName(tx.category.name)}` : ""}
              </span>
            </span>

            <span
              className={`shrink-0 text-sm font-medium tabular-nums ${
                isTransfer ? "text-text-muted" : isExpense ? "text-text-primary" : "text-success"
              }`}
            >
              {isTransfer ? "" : isExpense ? "-" : "+"}
              {formatCurrency(tx.amount)}
            </span>

            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(tx)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                onClick={() => onDelete(tx)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
              >
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
