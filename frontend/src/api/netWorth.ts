import { api } from "@/api/client";
import type { NetWorthRange, NetWorthSummary } from "@/types";

export function fetchNetWorthSummary(range: NetWorthRange) {
  return api.get<NetWorthSummary>(`/net-worth/summary?range=${range}`);
}
