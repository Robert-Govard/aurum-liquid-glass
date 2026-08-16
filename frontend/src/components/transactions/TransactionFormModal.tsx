import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useCreateTransaction, useUpdateTransaction } from "@/hooks/useTransactions";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction, TransactionInput, TransactionType } from "@/types";

interface TransactionFormModalProps {
  open: boolean;
  onClose: () => void;
  transaction?: Transaction | null;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  type: "expense" as TransactionType,
  account_id: "",
  category_id: "",
  transfer_account_id: "",
  amount: "",
  description: "",
  merchant: "",
  notes: "",
  date: todayIso(),
};

export function TransactionFormModal({ open, onClose, transaction }: TransactionFormModalProps) {
  const { t } = useTranslation();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const createTransaction = useCreateTransaction();
  const updateTransaction = useUpdateTransaction();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (transaction) {
      setForm({
        type: transaction.type,
        account_id: String(transaction.account_id),
        category_id: transaction.category_id ? String(transaction.category_id) : "",
        transfer_account_id: transaction.transfer_account_id ? String(transaction.transfer_account_id) : "",
        amount: transaction.amount,
        description: transaction.description,
        merchant: transaction.merchant ?? "",
        notes: transaction.notes ?? "",
        date: transaction.date,
      });
    } else {
      setForm({ ...EMPTY_FORM, account_id: accounts?.[0] ? String(accounts[0].id) : "" });
    }
    setError(null);
  }, [open, transaction, accounts]);

  const relevantCategories = (categories ?? []).filter((category) =>
    form.type === "income" ? category.kind === "income" : category.kind === "expense"
  );

  const isSaving = createTransaction.isPending || updateTransaction.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!form.account_id) {
      setError(t("transactions.form.errorSelectAccount"));
      return;
    }
    if (form.type === "transfer" && !form.transfer_account_id) {
      setError(t("transactions.form.errorSelectDestination"));
      return;
    }
    if (form.type === "transfer" && form.transfer_account_id === form.account_id) {
      setError(t("transactions.form.errorSameAccount"));
      return;
    }

    const payload: TransactionInput = {
      type: form.type,
      account_id: Number(form.account_id),
      category_id: form.type === "transfer" ? null : form.category_id ? Number(form.category_id) : null,
      transfer_account_id: form.type === "transfer" ? Number(form.transfer_account_id) : null,
      amount: form.amount,
      description: form.description,
      merchant: form.merchant || null,
      notes: form.notes || null,
      date: form.date,
    };

    try {
      if (transaction) {
        await updateTransaction.mutateAsync({ id: transaction.id, input: payload });
      } else {
        await createTransaction.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("transactions.form.saveError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={transaction ? t("transactions.form.editTitle") : t("transactions.form.newTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="type">{t("transactions.form.typeLabel")}</Label>
          <Select
            id="type"
            value={form.type}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, type: event.target.value as TransactionType, category_id: "" }))
            }
          >
            <option value="expense">{t("transactions.form.typeExpense")}</option>
            <option value="income">{t("transactions.form.typeIncome")}</option>
            <option value="transfer">{t("transactions.form.typeTransfer")}</option>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="amount">{t("transactions.form.amountLabel")}</Label>
            <Input
              id="amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="date">{t("transactions.form.dateLabel")}</Label>
            <Input
              id="date"
              type="date"
              required
              value={form.date}
              onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="description">{t("transactions.form.descriptionLabel")}</Label>
          <Input
            id="description"
            required
            placeholder={t("transactions.form.descriptionPlaceholder")}
            value={form.description}
            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="account">{t("transactions.form.accountLabel")}</Label>
          <Select
            id="account"
            required
            value={form.account_id}
            onChange={(event) => setForm((prev) => ({ ...prev, account_id: event.target.value }))}
          >
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </div>

        {form.type === "transfer" ? (
          <div>
            <Label htmlFor="transfer_account">{t("transactions.form.transferAccountLabel")}</Label>
            <Select
              id="transfer_account"
              required
              value={form.transfer_account_id}
              onChange={(event) => setForm((prev) => ({ ...prev, transfer_account_id: event.target.value }))}
            >
              <option value="" disabled>
                {t("transactions.form.selectAccount")}
              </option>
              {accounts
                ?.filter((account) => String(account.id) !== form.account_id)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
            </Select>
          </div>
        ) : (
          <div>
            <Label htmlFor="category">{t("transactions.form.categoryLabel")}</Label>
            <Select
              id="category"
              value={form.category_id}
              onChange={(event) => setForm((prev) => ({ ...prev, category_id: event.target.value }))}
            >
              <option value="">{t("transactions.form.noCategory")}</option>
              {relevantCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </Select>
          </div>
        )}

        <div>
          <Label htmlFor="merchant">{t("transactions.form.merchantLabel")}</Label>
          <Input
            id="merchant"
            value={form.merchant}
            onChange={(event) => setForm((prev) => ({ ...prev, merchant: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="notes">{t("transactions.form.notesLabel")}</Label>
          <Input
            id="notes"
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
