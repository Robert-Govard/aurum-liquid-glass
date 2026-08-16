import { api } from "@/api/client";
import type { Category } from "@/types";

export function fetchCategories() {
  return api.get<Category[]>("/categories");
}
