import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <PreferencesCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
    </div>
  );
}
