import { useState } from "react";
import { PillSelector } from "@/components/layout/PillSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { useTranslation } from "@/lib/i18n";

type RangePreset = "all" | "5y" | "12m" | "this_year";

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function computeRange(preset: RangePreset): { startDate?: string; endDate?: string } {
  const today = new Date();
  const end = isoDate(today);
  switch (preset) {
    case "all":
      return {};
    case "this_year":
      return { startDate: `${today.getFullYear()}-01-01`, endDate: end };
    case "12m": {
      const start = new Date(today.getFullYear(), today.getMonth() - 11, 1);
      return { startDate: isoDate(start), endDate: end };
    }
    case "5y": {
      const start = new Date(today.getFullYear() - 5, today.getMonth(), 1);
      return { startDate: isoDate(start), endDate: end };
    }
  }
}

export function CashFlowPage() {
  const { t } = useTranslation();
  const [range, setRange] = useState<RangePreset>("12m");
  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "5y", label: t("reports.range5y") },
    { value: "12m", label: t("reports.range12m") },
    { value: "this_year", label: t("reports.rangeThisYear") },
  ];

  const { startDate, endDate } = computeRange(range);
  const { data: cashFlow, isLoading } = useCashFlow(startDate, endDate);

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <PillSelector options={RANGE_OPTIONS} value={range} onChange={setRange} />
      </div>

      <CashFlowChart cashFlow={cashFlow} isLoading={isLoading} />
    </div>
  );
}
