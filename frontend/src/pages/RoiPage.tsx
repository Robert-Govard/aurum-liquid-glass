import { useState } from "react";
import { RoiCalculatorCard } from "@/components/roi/RoiCalculatorCard";
import { RoiProjectionCard } from "@/components/roi/RoiProjectionCard";
import { PremiumRequired } from "@/components/premium/PremiumRequired";
import { useAuthState } from "@/lib/auth";

export function RoiPage() {
  const { user } = useAuthState();
  if (!user?.is_premium) return <PremiumRequired />;
  return <RoiPageContent />;
}

function RoiPageContent() {
  const [investment, setInvestment] = useState("");
  const [monthlyIncome, setMonthlyIncome] = useState("");

  const investmentAmount = Number(investment);
  const monthlyAmount = Number(monthlyIncome);
  const hasInputs = investment !== "" && monthlyIncome !== "" && investmentAmount > 0;

  const annualIncome = monthlyAmount * 12;
  const annualRoiPercent = hasInputs ? (annualIncome / investmentAmount) * 100 : null;
  const paybackYears = annualRoiPercent !== null && annualIncome > 0 ? investmentAmount / annualIncome : null;

  return (
    <div className="space-y-5">
      <RoiCalculatorCard
        investment={investment}
        onInvestmentChange={setInvestment}
        monthlyIncome={monthlyIncome}
        onMonthlyIncomeChange={setMonthlyIncome}
        annualRoiPercent={annualRoiPercent}
        paybackYears={paybackYears}
      />

      {annualRoiPercent !== null && (
        <RoiProjectionCard
          investmentAmount={investmentAmount}
          annualIncome={annualIncome}
          annualRoiPercent={annualRoiPercent}
        />
      )}
    </div>
  );
}
