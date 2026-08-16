import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategoryRankingItem } from "@/types";

interface CategoryRankingCardProps {
  items: CategoryRankingItem[];
  isLoading: boolean;
  selectedCategoryId: number | null;
  onSelectCategory: (categoryId: number) => void;
}

/** Ranks every expense category by total spent over the currently selected
 * period — unlike the Dashboard breakdown (locked to one month) or the
 * detail chart below (locked to one category), this is "which category
 * costs the most" across the whole range at once. Clicking a row drills
 * into that category in the detail chart/transaction list below. */
export function CategoryRankingCard({ items, isLoading, selectedCategoryId, onSelectCategory }: CategoryRankingCardProps) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("reports.categoryRankingTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("reports.noRankingData")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {items.map((item, index) => {
              const Icon = getCategoryIcon(item.icon);
              const isSelected = item.category_id === selectedCategoryId;
              return (
                <li key={item.category_id}>
                  <button
                    type="button"
                    onClick={() => onSelectCategory(item.category_id)}
                    className={`flex w-full items-center gap-3 rounded-lg py-2.5 text-left transition-colors hover:bg-surface-2 ${
                      isSelected ? "bg-surface-2" : ""
                    }`}
                  >
                    <span className="w-4 shrink-0 text-right text-xs tabular-nums text-text-muted">{index + 1}</span>
                    <span
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                      style={{ backgroundColor: `${item.color}26` }}
                    >
                      <Icon size={15} style={{ color: item.color }} />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                      {translateCategoryName(item.name)}
                    </span>
                    <span className="hidden w-24 shrink-0 items-center gap-2 sm:flex">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <span
                          className="block h-full rounded-full"
                          style={{ width: `${item.percent}%`, backgroundColor: item.color }}
                        />
                      </span>
                      <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">
                        {item.percent.toFixed(0)}%
                      </span>
                    </span>
                    <span className="shrink-0 pr-1 text-sm font-medium tabular-nums text-text-primary">
                      {formatCurrency(item.amount)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
