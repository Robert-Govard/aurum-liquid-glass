import { Pencil, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { useTranslation } from "@/lib/i18n";
import type { Category } from "@/types";

interface CategoryListProps {
  items: Category[];
  onEdit: (category: Category) => void;
  onDelete: (category: Category) => void;
}

export function CategoryList({ items, onEdit, onDelete }: CategoryListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-text-muted">{t("category.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((category) => {
        const Icon = getCategoryIcon(category.icon);

        return (
          <li key={category.id} className="flex items-center gap-3 py-2.5">
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
              style={{ backgroundColor: `${category.color}1a`, color: category.color }}
            >
              <Icon size={15} />
            </span>
            <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-sm font-medium text-text-primary">
              <span className="truncate">{category.name}</span>
              {category.is_default && (
                <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                  {t("category.defaultBadge")}
                </span>
              )}
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(category)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                title={category.is_default ? t("category.defaultCannotDelete") : undefined}
                disabled={category.is_default}
                onClick={() => onDelete(category)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-text-muted"
              >
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
