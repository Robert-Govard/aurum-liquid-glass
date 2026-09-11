import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdminUser, fetchAdminUserDashboard, fetchAdminUsers, updateAdminUser } from "@/api/admin";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
}

export function useAdminUserDashboard(userId: number | null, year: number, month: number) {
  return useQuery({
    queryKey: ["admin-user-dashboard", userId, year, month],
    queryFn: () => fetchAdminUserDashboard(userId as number, year, month),
    // Same conditional-query pattern already used in hooks/useCrypto.ts and
    // hooks/useReports.ts — don't fire a request with a nonsense id before
    // any user has been selected in the admin list.
    enabled: userId !== null,
  });
}

export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) => updateAdminUser(id, { is_active: isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useDeleteAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteAdminUser(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}
