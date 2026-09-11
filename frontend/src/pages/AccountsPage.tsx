import { useState } from "react";
import { Plus } from "lucide-react";
import { AccountList } from "@/components/accounts/AccountList";
import { AccountFormModal } from "@/components/accounts/AccountFormModal";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Switch } from "@/components/ui/Switch";
import { useAccounts, useDeleteAccount, useUpdateAccount } from "@/hooks/useAccounts";
import { useTranslation } from "@/lib/i18n";
import type { Account, AccountWithBalance } from "@/types";

export function AccountsPage() {
  const { t } = useTranslation();
  const [showArchived, setShowArchived] = useState(false);
  const { data: accounts, isLoading } = useAccounts(showArchived);
  const updateAccount = useUpdateAccount();
  const deleteAccount = useDeleteAccount();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);

  function openCreateModal() {
    setEditingAccount(null);
    setModalOpen(true);
  }

  function openEditModal(account: Account) {
    setEditingAccount(account);
    setModalOpen(true);
  }

  function handleToggleArchived(account: AccountWithBalance) {
    updateAccount.mutate({ id: account.id, input: { is_archived: !account.is_archived } });
  }

  function handleDelete(account: AccountWithBalance) {
    if (window.confirm(t("account.confirmDelete", { name: account.name }))) {
      deleteAccount.mutate(account.id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.accounts")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
            <Switch checked={showArchived} onChange={setShowArchived} aria-label={t("account.showArchived")} />
            {t("account.showArchived")}
          </div>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AccountList
              items={accounts ?? []}
              onEdit={openEditModal}
              onToggleArchived={handleToggleArchived}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <AccountFormModal open={modalOpen} onClose={() => setModalOpen(false)} account={editingAccount} />
    </div>
  );
}
