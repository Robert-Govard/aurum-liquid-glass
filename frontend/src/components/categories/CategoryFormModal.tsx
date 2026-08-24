import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { CategoryColorPicker } from "@/components/categories/CategoryColorPicker";
import { CategoryIconPicker } from "@/components/categories/CategoryIconPicker";
import { useCreateCategory, useUpdateCategory } from "@/hooks/useCategories";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Category, CategoryKind } from "@/types";

interface CategoryFormModalProps {
  open: boolean;
  onClose: () => void;
  category?: Category | null;
  // Preselects kind for a new category — irrelevant once editing, since kind
  // can't change after creation (see backend CategoryUpdate schema).
  defaultKind: CategoryKind;
}

const KINDS: CategoryKind[] = ["expense", "income"];

function emptyForm(kind: CategoryKind) {
  return { name: "", kind, icon: "wallet", color: "#2a78d6" };
}

export function CategoryFormModal({ open, onClose, category, defaultKind }: CategoryFormModalProps) {
  const { t } = useTranslation();
  const createCategory = useCreateCategory();
  const updateCategory = useUpdateCategory();

  const [form, setForm] = useState(emptyForm(defaultKind));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm(
      category
        ? { name: category.name, kind: category.kind, icon: category.icon ?? "wallet", color: category.color }
        : emptyForm(defaultKind)
    );
    setError(null);
  }, [open, category, defaultKind]);

  const isSaving = createCategory.isPending || updateCategory.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      if (category) {
        await updateCategory.mutateAsync({
          id: category.id,
          input: { name: form.name, icon: form.icon, color: form.color },
        });
      } else {
        await createCategory.mutateAsync(form);
      }
      onClose();
    } catch {
      setError(t("category.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={category ? t("category.form.editTitle") : t("category.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="category-name">{t("category.form.nameLabel")}</Label>
          <Input
            id="category-name"
            required
            placeholder={t("category.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="category-kind">{t("category.form.kindLabel")}</Label>
          <Select
            id="category-kind"
            value={form.kind}
            disabled={Boolean(category)}
            onChange={(event) => setForm((prev) => ({ ...prev, kind: event.target.value as CategoryKind }))}
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {t(`category.kind.${kind}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label>{t("category.form.iconLabel")}</Label>
          <CategoryIconPicker value={form.icon} onChange={(icon) => setForm((prev) => ({ ...prev, icon }))} />
        </div>

        <div>
          <Label>{t("category.form.colorLabel")}</Label>
          <CategoryColorPicker value={form.color} onChange={(color) => setForm((prev) => ({ ...prev, color }))} />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
