import { api } from "@/api/client";
import type { DashboardSummary } from "@/types";

export function fetchDashboardSummary(year: number, month: number) {
  return api.get<DashboardSummary>(`/dashboard/summary?year=${year}&month=${month}`);
}
