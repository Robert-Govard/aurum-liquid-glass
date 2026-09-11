import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { AdminUserDashboardModal } from "@/components/admin/AdminUserDashboardModal";
import { AdminUserList } from "@/components/admin/AdminUserList";
import { useAdminUsers, useDeleteAdminUser, useUpdateAdminUser } from "@/hooks/useAdmin";
import { useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import type { AdminUser } from "@/types";

export function AdminPage() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuthState();
  const { data: users, isLoading, isError } = useAdminUsers();
  const updateUser = useUpdateAdminUser();
  const deleteUser = useDeleteAdminUser();
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  function handleToggleActive(user: AdminUser) {
    updateUser.mutate({ id: user.id, isActive: !user.is_active });
  }

  function handleDelete(user: AdminUser) {
    if (window.confirm(t("admin.confirmDelete", { email: user.email }))) {
      deleteUser.mutate(user.id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.admin")}</CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
              {t("admin.loadError")}
            </p>
          ) : isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AdminUserList
              items={users ?? []}
              currentUserId={currentUser?.id}
              onView={setSelectedUser}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>
      <AdminUserDashboardModal user={selectedUser} onClose={() => setSelectedUser(null)} />
    </div>
  );
}
