import { useQuery } from "@tanstack/react-query";
import { fetchFinancialAlerts } from "@/api/insights";

export function useFinancialAlerts() {
  return useQuery({
    queryKey: ["financial-alerts"],
    queryFn: fetchFinancialAlerts,
  });
}
