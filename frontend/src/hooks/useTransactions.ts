import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTransaction,
  deleteTransaction,
  fetchTransactions,
  fetchTransactionYears,
  updateTransaction,
  type TransactionFilters,
} from "@/api/transactions";
import type { TransactionInput } from "@/types";

function useInvalidateAfterTransactionChange() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["transaction-years"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
    queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
    queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
    queryClient.invalidateQueries({ queryKey: ["budget-status"] });
    queryClient.invalidateQueries({ queryKey: ["financial-alerts"] });
    queryClient.invalidateQueries({ queryKey: ["advice"] });
    queryClient.invalidateQueries({ queryKey: ["cash-flow"] });
  };
}

export function useTransactions(filters: TransactionFilters) {
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => fetchTransactions(filters),
  });
}

export function useTransactionYears() {
  return useQuery({
    queryKey: ["transaction-years"],
    queryFn: fetchTransactionYears,
  });
}

export function useCreateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (input: TransactionInput) => createTransaction(input),
    onSuccess: invalidate,
  });
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<TransactionInput> }) =>
      updateTransaction(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (id: number) => deleteTransaction(id),
    onSuccess: invalidate,
  });
}
