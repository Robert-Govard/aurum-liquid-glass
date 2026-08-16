import { api } from "@/api/client";
import type { FinancialAlert } from "@/types";

export function fetchFinancialAlerts() {
  return api.get<{ alerts: FinancialAlert[] }>("/insights/alerts");
}
