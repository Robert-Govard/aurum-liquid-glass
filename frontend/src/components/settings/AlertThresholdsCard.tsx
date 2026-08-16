import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { useTranslation } from "@/lib/i18n";
import { useAppSettings, useUpdateAppSettings } from "@/hooks/useSettings";

const MIN_MONTHS = 1;
const MAX_MONTHS = 24;
const MIN_PERCENT = 1;
const MAX_PERCENT = 100;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function AlertThresholdsCard() {
  const { t } = useTranslation();
  const { data: settings } = useAppSettings();
  const updateSettings = useUpdateAppSettings();

  const [cashFlowMonths, setCashFlowMonths] = useState("");
  const [netWorthMonths, setNetWorthMonths] = useState("");
  const [riskyPercent, setRiskyPercent] = useState("");

  useEffect(() => {
    if (!settings) return;
    setCashFlowMonths(String(settings.negative_cash_flow_threshold_months));
    setNetWorthMonths(String(settings.net_worth_decline_threshold_months));
    setRiskyPercent(String(settings.risky_allocation_threshold_percent));
  }, [settings]);

  function commitCashFlowMonths() {
    const value = clamp(Number(cashFlowMonths) || MIN_MONTHS, MIN_MONTHS, MAX_MONTHS);
    setCashFlowMonths(String(value));
    if (settings && value !== settings.negative_cash_flow_threshold_months) {
      updateSettings.mutate({ negative_cash_flow_threshold_months: value });
    }
  }

  function commitNetWorthMonths() {
    const value = clamp(Number(netWorthMonths) || MIN_MONTHS, MIN_MONTHS, MAX_MONTHS);
    setNetWorthMonths(String(value));
    if (settings && value !== settings.net_worth_decline_threshold_months) {
      updateSettings.mutate({ net_worth_decline_threshold_months: value });
    }
  }

  function commitRiskyPercent() {
    const value = clamp(Number(riskyPercent) || MIN_PERCENT, MIN_PERCENT, MAX_PERCENT);
    setRiskyPercent(String(value));
    if (settings && value !== settings.risky_allocation_threshold_percent) {
      updateSettings.mutate({ risky_allocation_threshold_percent: value });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.alertsTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <Label htmlFor="cash-flow-threshold">{t("settings.negativeCashFlowThresholdLabel")}</Label>
            <Input
              id="cash-flow-threshold"
              type="number"
              min={MIN_MONTHS}
              max={MAX_MONTHS}
              step={1}
              value={cashFlowMonths}
              onChange={(event) => setCashFlowMonths(event.target.value)}
              onBlur={commitCashFlowMonths}
            />
          </div>
          <div>
            <Label htmlFor="net-worth-threshold">{t("settings.netWorthDeclineThresholdLabel")}</Label>
            <Input
              id="net-worth-threshold"
              type="number"
              min={MIN_MONTHS}
              max={MAX_MONTHS}
              step={1}
              value={netWorthMonths}
              onChange={(event) => setNetWorthMonths(event.target.value)}
              onBlur={commitNetWorthMonths}
            />
          </div>
          <div>
            <Label htmlFor="risky-allocation-threshold">{t("settings.riskyAllocationThresholdLabel")}</Label>
            <Input
              id="risky-allocation-threshold"
              type="number"
              min={MIN_PERCENT}
              max={MAX_PERCENT}
              step={1}
              value={riskyPercent}
              onChange={(event) => setRiskyPercent(event.target.value)}
              onBlur={commitRiskyPercent}
            />
          </div>
        </div>
        <p className="text-xs text-text-muted">{t("settings.alertsHint")}</p>
      </CardContent>
    </Card>
  );
}
