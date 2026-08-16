import { useQuery } from "@tanstack/react-query";
import { fetchDashboardSummary } from "@/api/dashboard";

export function useDashboardSummary(year: number, month: number) {
  return useQuery({
    queryKey: ["dashboard-summary", year, month],
    queryFn: () => fetchDashboardSummary(year, month),
  });
}
