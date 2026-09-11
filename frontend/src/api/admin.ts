import { api } from "@/api/client";
import type { AdminUser } from "@/types";

export function fetchAdminUsers() {
  return api.get<AdminUser[]>("/admin/users");
}

export function updateAdminUser(id: number, input: { is_active: boolean }) {
  return api.patch<AdminUser>(`/admin/users/${id}`, input);
}

export function deleteAdminUser(id: number) {
  return api.delete<void>(`/admin/users/${id}`);
}
