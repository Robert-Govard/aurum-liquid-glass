import { api } from "@/api/client";
import type { AdminUser, DashboardSummary } from "@/types";

export function fetchAdminUsers() {
  return api.get<AdminUser[]>("/admin/users");
}

export function updateAdminUser(id: number, input: { is_active: boolean }) {
  return api.patch<AdminUser>(`/admin/users/${id}`, input);
}

export function deleteAdminUser(id: number) {
  return api.delete<void>(`/admin/users/${id}`);
}

export function updateAdminUserPremium(id: number, premiumUntil: string | null) {
  return api.patch<AdminUser>(`/admin/users/${id}/premium`, { premium_until: premiumUntil });
}

export function fetchAdminUserDashboard(userId: number, year: number, month: number) {
  return api.get<DashboardSummary>(`/admin/users/${userId}/dashboard-summary?year=${year}&month=${month}`);
}
