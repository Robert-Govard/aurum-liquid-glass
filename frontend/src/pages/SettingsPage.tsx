import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { LanguageCard } from "@/components/settings/LanguageCard";

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <LanguageCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
    </div>
  );
}
