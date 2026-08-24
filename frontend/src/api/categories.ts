import { api } from "@/api/client";
import type { Category, CategoryInput, CategoryUpdateInput } from "@/types";

export function fetchCategories() {
  return api.get<Category[]>("/categories");
}

export function createCategory(input: CategoryInput) {
  return api.post<Category>("/categories", input);
}

export function updateCategory(id: number, input: CategoryUpdateInput) {
  return api.patch<Category>(`/categories/${id}`, input);
}

export function deleteCategory(id: number) {
  return api.delete<void>(`/categories/${id}`);
}
