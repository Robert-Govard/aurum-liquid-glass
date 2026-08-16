import { useQuery } from "@tanstack/react-query";
import { fetchCashFlow } from "@/api/cashFlow";

export function useCashFlow(startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["cash-flow", startDate, endDate],
    queryFn: () => fetchCashFlow(startDate, endDate),
  });
}
