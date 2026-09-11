import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAdminUser, fetchAdminUsers, updateAdminUser } from "@/api/admin";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin-users"], queryFn: fetchAdminUsers });
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
