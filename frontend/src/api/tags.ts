import { api } from "@/api/client";
import type { Tag } from "@/types";

export function fetchTags() {
  return api.get<Tag[]>("/tags");
}

export function createTag(name: string) {
  return api.post<Tag>("/tags", { name });
}

export function deleteTag(id: number) {
  return api.delete<void>(`/tags/${id}`);
}
