import { api } from "@/api/client";
import type { Transaction, TransactionInput, TransactionPage } from "@/types";

export type TransactionSort = "date_desc" | "amount_desc" | "amount_asc";

export interface TransactionFilters {
  year?: number;
  month?: number;
  start_date?: string;
  end_date?: string;
  account_id?: number;
  category_id?: number;
  type?: string;
  sort?: TransactionSort;
  page?: number;
  page_size?: number;
}

export function fetchTransactions(filters: TransactionFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null) params.set(key, String(value));
  });
  return api.get<TransactionPage>(`/transactions?${params.toString()}`);
}

export function createTransaction(input: TransactionInput) {
  return api.post<Transaction>("/transactions", input);
}

export function updateTransaction(id: number, input: Partial<TransactionInput>) {
  return api.patch<Transaction>(`/transactions/${id}`, input);
}

export function deleteTransaction(id: number) {
  return api.delete<void>(`/transactions/${id}`);
}
