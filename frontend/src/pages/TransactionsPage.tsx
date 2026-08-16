import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Input";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useTransactions, useDeleteTransaction, useTransactionYears } from "@/hooks/useTransactions";
import { useCategories } from "@/hooks/useCategories";
import type { TransactionSort } from "@/api/transactions";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction, TransactionType } from "@/types";

const PAGE_SIZE = 20;

/** Clamp a query-param month to 1-12, falling back to `fallback` for
 * anything missing or out of range (e.g. a hand-edited URL). */
function parseMonthParam(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? Math.min(12, Math.max(1, parsed)) : fallback;
}

function parseYearParam(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function TransactionsPage() {
  const { t } = useTranslation();
  const now = new Date();
  // Deep-linked from the Dashboard's "All transactions" link, which carries
  // the month/year the user was already looking at (?year=&month=) so this
  // page doesn't reset back to the current month.
  const [searchParams] = useSearchParams();
  const [year, setYear] = useState(() => parseYearParam(searchParams.get("year"), now.getFullYear()));
  const [month, setMonth] = useState(() => parseMonthParam(searchParams.get("month"), now.getMonth() + 1));
  const [type, setType] = useState<TransactionType | "">("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

  const { data: categories } = useCategories();
  const { data: years } = useTransactionYears();
  const { data, isLoading, isError } = useTransactions({
    year,
    month,
    type: type || undefined,
    category_id: categoryId ? Number(categoryId) : undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const deleteTransaction = useDeleteTransaction();

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  function openCreateModal() {
    setEditingTransaction(null);
    setModalOpen(true);
  }

  function openEditModal(transaction: Transaction) {
    setEditingTransaction(transaction);
    setModalOpen(true);
  }

  function handleDelete(transaction: Transaction) {
    if (window.confirm(t("transactions.confirmDelete", { description: transaction.description }))) {
      deleteTransaction.mutate(transaction.id);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="min-w-0 flex-1">
            <MonthSelector
              month={month}
              onChange={(value) => {
                setMonth(value);
                setPage(1);
              }}
            />
          </div>
          <YearSelector
            years={years ?? [now.getFullYear()]}
            year={year}
            onChange={(value) => {
              setYear(value);
              setPage(1);
            }}
          />
        </div>
        <Button onClick={openCreateModal} className="w-full sm:w-auto">
          <Plus size={16} />
          {t("transactions.addButton")}
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Select
          value={type}
          onChange={(event) => {
            setType(event.target.value as TransactionType | "");
            setPage(1);
          }}
          className="sm:w-48"
        >
          <option value="">{t("transactions.allTypes")}</option>
          <option value="expense">{t("transactions.expense")}</option>
          <option value="income">{t("transactions.income")}</option>
          <option value="transfer">{t("transactions.transfer")}</option>
        </Select>
        <Select
          value={categoryId}
          onChange={(event) => {
            setCategoryId(event.target.value);
            setPage(1);
          }}
          className="sm:w-56"
        >
          <option value="">{t("transactions.allCategories")}</option>
          {categories?.map((category) => (
            <option key={category.id} value={category.id}>
              {translateCategoryName(category.name)}
            </option>
          ))}
        </Select>
        <Select
          value={sort}
          onChange={(event) => {
            setSort(event.target.value as TransactionSort);
            setPage(1);
          }}
          className="sm:w-56"
        >
          <option value="date_desc">{t("transactions.sortDateDesc")}</option>
          <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
          <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nav.transactions")}</CardTitle>
          {data && <span className="text-xs text-text-muted">{t("common.totalCount", { count: data.total })}</span>}
        </CardHeader>
        <CardContent>
          {isError && <p className="py-6 text-center text-sm text-danger">{t("transactions.failedToLoad")}</p>}
          {isLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <TransactionsTable items={data?.items ?? []} onEdit={openEditModal} onDelete={handleDelete} />
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("common.back")}
              </Button>
              <span className="text-text-muted">{t("common.pageOf", { page, total: totalPages })}</span>
              <Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                {t("common.next")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionFormModal open={modalOpen} onClose={() => setModalOpen(false)} transaction={editingTransaction} />
    </div>
  );
}
