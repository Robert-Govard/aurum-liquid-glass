import { useQuery } from "@tanstack/react-query";
import { fetchNetWorthSummary } from "@/api/netWorth";
import type { NetWorthRange } from "@/types";

export function useNetWorthSummary(range: NetWorthRange) {
  return useQuery({
    queryKey: ["net-worth-summary", range],
    queryFn: () => fetchNetWorthSummary(range),
  });
}
