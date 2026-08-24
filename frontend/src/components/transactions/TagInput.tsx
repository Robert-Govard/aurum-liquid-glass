import { useRef, useState } from "react";
import { X } from "lucide-react";
import { useCreateTag, useTags } from "@/hooks/useTags";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Tag } from "@/types";

interface TagInputProps {
  value: Tag[];
  onChange: (tags: Tag[]) => void;
}

// Free-text, multi-select tag picker with inline create — types like an
// autocomplete, Enter either picks the top matching existing tag or creates
// a new one (the backend dedupes case-insensitively either way, see
// routes/tags.py). No dedicated tag-management page yet: renaming/deleting a
// tag globally isn't exposed here, only removing it from this transaction.
export function TagInput({ value, onChange }: TagInputProps) {
  const { t } = useTranslation();
  const { data: allTags } = useTags();
  const createTag = useCreateTag();

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedIds = new Set(value.map((tag) => tag.id));
  const trimmedQuery = query.trim();
  const suggestions = (allTags ?? [])
    .filter((tag) => !selectedIds.has(tag.id))
    .filter((tag) => (trimmedQuery ? tag.name.toLowerCase().includes(trimmedQuery.toLowerCase()) : true))
    .slice(0, 8);
  const exactMatch = (allTags ?? []).find((tag) => tag.name.toLowerCase() === trimmedQuery.toLowerCase());

  function addTag(tag: Tag) {
    onChange([...value, tag]);
    setQuery("");
    setOpen(false);
    inputRef.current?.focus();
  }

  function removeTag(tagId: number) {
    onChange(value.filter((tag) => tag.id !== tagId));
  }

  async function commitQuery() {
    if (!trimmedQuery) return;
    if (exactMatch) {
      addTag(exactMatch);
      return;
    }
    const created = await createTag.mutateAsync(trimmedQuery);
    addTag(created);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      if (suggestions[0]) addTag(suggestions[0]);
      else void commitQuery();
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Backspace" && !query && value.length > 0) {
      removeTag(value[value.length - 1].id);
    }
  }

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-2 py-1.5 focus-within:border-series-1">
        {value.map((tag) => (
          <span
            key={tag.id}
            className="flex items-center gap-1 rounded-full bg-surface-2 py-0.5 pl-2 pr-1 text-xs text-text-secondary"
          >
            {tag.name}
            <button
              type="button"
              aria-label={t("transactions.form.removeTag", { name: tag.name })}
              onClick={() => removeTag(tag.id)}
              className="rounded-full p-0.5 text-text-muted hover:bg-surface-1 hover:text-text-primary"
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          className="h-6 min-w-[8ch] flex-1 border-none bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
          value={query}
          placeholder={value.length === 0 ? t("transactions.form.tagsPlaceholder") : ""}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 100)}
          onKeyDown={handleKeyDown}
        />
      </div>

      {open && (suggestions.length > 0 || (trimmedQuery && !exactMatch)) && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface-1 shadow-lg">
          {suggestions.map((tag) => (
            <li key={tag.id}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => addTag(tag)}
                className={cn("block w-full px-3 py-1.5 text-left text-sm text-text-primary hover:bg-surface-2")}
              >
                {tag.name}
              </button>
            </li>
          ))}
          {trimmedQuery && !exactMatch && (
            <li>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => void commitQuery()}
                className="block w-full px-3 py-1.5 text-left text-sm text-series-1 hover:bg-surface-2"
              >
                {t("transactions.form.createTag", { name: trimmedQuery })}
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
