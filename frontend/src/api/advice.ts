import { api } from "@/api/client";
import type { AdviceResponse } from "@/types";

export function fetchAdvice() {
  return api.get<AdviceResponse>("/advice");
}
