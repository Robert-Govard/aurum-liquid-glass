import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { useTranslation } from "@/lib/i18n";

interface RoiCalculatorCardProps {
  investment: string;
  onInvestmentChange: (value: string) => void;
  monthlyIncome: string;
  onMonthlyIncomeChange: (value: string) => void;
  annualRoiPercent: number | null;
  paybackYears: number | null;
}

/** Quick "is this a good deal" check — purchase price + expected monthly
 * income in, annual return % and payback period out. Purely a scratchpad:
 * not tied to any Asset, doesn't persist, doesn't read anything else you've
 * tracked in the app — only these two numbers. Same formula AssetsTable
 * already shows inline for assets that have monthly_cash_flow set, just
 * usable before you've committed to adding one. The multi-year, compound-
 * interest projection built from these same numbers lives in
 * RoiProjectionCard, rendered alongside this one on RoiPage. */
export function RoiCalculatorCard({
  investment,
  onInvestmentChange,
  monthlyIncome,
  onMonthlyIncomeChange,
  annualRoiPercent,
  paybackYears,
}: RoiCalculatorCardProps) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("roi.calculator.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="roi-investment">{t("roi.calculator.investmentLabel")}</Label>
            <Input
              id="roi-investment"
              type="number"
              step="0.01"
              min="0"
              placeholder="100000"
              value={investment}
              onChange={(event) => onInvestmentChange(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="roi-income">{t("roi.calculator.monthlyIncomeLabel")}</Label>
            <Input
              id="roi-income"
              type="number"
              step="0.01"
              placeholder="830"
              value={monthlyIncome}
              onChange={(event) => onMonthlyIncomeChange(event.target.value)}
            />
          </div>
        </div>

        {annualRoiPercent === null ? (
          <p className="text-xs text-text-muted">{t("roi.calculator.hint")}</p>
        ) : (
          <div className="rounded-lg bg-surface-2 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {t("roi.calculator.annualRoiLabel")}
            </p>
            <p
              className="mt-1 text-2xl font-semibold tabular-nums"
              style={{ color: annualRoiPercent >= 0 ? "var(--success)" : "var(--danger)" }}
            >
              {annualRoiPercent.toFixed(1)}%
            </p>
            <p className="mt-1 text-xs text-text-muted">
              {paybackYears !== null
                ? t("roi.calculator.payback", { years: paybackYears.toFixed(1) })
                : t("roi.calculator.noPayback")}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
