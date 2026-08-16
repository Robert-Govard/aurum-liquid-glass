import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { LanguageCard } from "@/components/settings/LanguageCard";
import { ThemeCard } from "@/components/settings/ThemeCard";

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <ThemeCard />
      <LanguageCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
    </div>
  );
}
