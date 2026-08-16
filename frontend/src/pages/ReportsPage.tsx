import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { PillSelector } from "@/components/layout/PillSelector";
import { CategoryRankingCard } from "@/components/reports/CategoryRankingCard";
import { CategorySpendingChart } from "@/components/reports/CategorySpendingChart";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useCategories } from "@/hooks/useCategories";
import { useCategoryRanking, useCategorySpendingReport } from "@/hooks/useReports";
import { useDeleteTransaction, useTransactions } from "@/hooks/useTransactions";
import type { TransactionSort } from "@/api/transactions";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction } from "@/types";

type RangePreset = "all" | "5y" | "12m" | "this_year";

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function computeRange(preset: RangePreset): { startDate?: string; endDate?: string } {
  const today = new Date();
  const end = isoDate(today);
  switch (preset) {
    case "all":
      return {};
    case "this_year":
      return { startDate: `${today.getFullYear()}-01-01`, endDate: end };
    case "12m": {
      const start = new Date(today.getFullYear(), today.getMonth() - 11, 1);
      return { startDate: isoDate(start), endDate: end };
    }
    case "5y": {
      const start = new Date(today.getFullYear() - 5, today.getMonth(), 1);
      return { startDate: isoDate(start), endDate: end };
    }
  }
}

const PAGE_SIZE = 20;

export function ReportsPage() {
  const { t } = useTranslation();
  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "5y", label: t("reports.range5y") },
    { value: "12m", label: t("reports.range12m") },
    { value: "this_year", label: t("reports.rangeThisYear") },
  ];
  const { data: categories } = useCategories();
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [range, setRange] = useState<RangePreset>("all");
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (categoryId === null && categories && categories.length > 0) {
      const firstExpense = categories.find((category) => category.kind === "expense");
      setCategoryId((firstExpense ?? categories[0]).id);
    }
  }, [categories, categoryId]);

  const { startDate, endDate } = computeRange(range);
  const { data: ranking, isLoading: isRankingLoading } = useCategoryRanking("expense", startDate, endDate);
  const { data: report, isLoading: isReportLoading } = useCategorySpendingReport(categoryId, startDate, endDate);
  const { data: transactions, isLoading: isTransactionsLoading } = useTransactions({
    category_id: categoryId ?? undefined,
    start_date: startDate,
    end_date: endDate,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const deleteTransaction = useDeleteTransaction();

  const expenseCategories = categories?.filter((category) => category.kind === "expense") ?? [];
  const incomeCategories = categories?.filter((category) => category.kind === "income") ?? [];
  const totalPages = transactions ? Math.max(1, Math.ceil(transactions.total / PAGE_SIZE)) : 1;

  function handleEdit(transaction: Transaction) {
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-xs flex-1">
          <Label htmlFor="report-category">{t("reports.categoryLabel")}</Label>
          <Select
            id="report-category"
            value={categoryId ?? ""}
            onChange={(event) => {
              setCategoryId(Number(event.target.value));
              setPage(1);
            }}
          >
            {expenseCategories.length > 0 && (
              <optgroup label={t("reports.expenseGroup")}>
                {expenseCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {translateCategoryName(category.name)}
                  </option>
                ))}
              </optgroup>
            )}
            {incomeCategories.length > 0 && (
              <optgroup label={t("reports.incomeGroup")}>
                {incomeCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {translateCategoryName(category.name)}
                  </option>
                ))}
              </optgroup>
            )}
          </Select>
        </div>
        <PillSelector
          options={RANGE_OPTIONS}
          value={range}
          onChange={(value) => {
            setRange(value);
            setPage(1);
          }}
        />
      </div>

      <CategoryRankingCard
        items={ranking?.items ?? []}
        isLoading={isRankingLoading}
        selectedCategoryId={categoryId}
        onSelectCategory={(id) => {
          setCategoryId(id);
          setPage(1);
        }}
      />

      <CategorySpendingChart report={report} isLoading={isReportLoading} />

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.transactionsTitle")}</CardTitle>
          {transactions && (
            <span className="text-xs text-text-muted">{t("common.totalCount", { count: transactions.total })}</span>
          )}
        </CardHeader>
        <CardContent>
          <Select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as TransactionSort);
              setPage(1);
            }}
            className="mb-3 sm:w-56"
          >
            <option value="date_desc">{t("transactions.sortDateDesc")}</option>
            <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
            <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
          </Select>
          {isTransactionsLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <TransactionsTable items={transactions?.items ?? []} onEdit={handleEdit} onDelete={handleDelete} />
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

      <TransactionFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        transaction={editingTransaction}
      />
    </div>
  );
}
