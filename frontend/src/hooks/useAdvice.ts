import { useQuery } from "@tanstack/react-query";
import { fetchAdvice } from "@/api/advice";

export function useAdvice() {
  return useQuery({ queryKey: ["advice"], queryFn: fetchAdvice });
}
