import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategoryBreakdownItem } from "@/types";

interface SpendingByCategoryCardProps {
  items: CategoryBreakdownItem[];
}

function DonutTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: CategoryBreakdownItem }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-text-primary">{translateCategoryName(item.name)}</p>
      <p className="text-text-secondary">
        {formatCurrency(item.amount)} · {item.percent.toFixed(1)}%
      </p>
    </div>
  );
}

export function SpendingByCategoryCard({ items }: SpendingByCategoryCardProps) {
  const { t } = useTranslation();
  const hasData = items.length > 0;
  // Recharts needs a numeric dataKey — API amounts arrive as strings (Decimal
  // is serialized as string to avoid float precision loss).
  const chartData = items.map((item) => ({ ...item, amount: Number(item.amount) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("dashboard.spendingByCategoryTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("dashboard.noExpensesThisMonth")}</p>
        ) : (
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
            <div className="h-56 w-56 shrink-0 sm:h-64 sm:w-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="amount"
                    nameKey="name"
                    innerRadius="62%"
                    outerRadius="100%"
                    paddingAngle={2}
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {items.map((item) => (
                      <Cell key={item.category_id ?? "other"} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <ul className="w-full min-w-0 flex-1 divide-y divide-gridline">
              {items.map((item) => {
                const Icon = getCategoryIcon(item.icon);
                return (
                  <li
                    key={item.category_id ?? "other"}
                    className="flex items-center gap-3 py-2 first:pt-0 last:pb-0"
                  >
                    <span
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                      style={{ backgroundColor: `${item.color}26` }}
                    >
                      <Icon size={14} style={{ color: item.color }} />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                      {translateCategoryName(item.name)}
                    </span>
                    <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                      {formatCurrency(item.amount)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
