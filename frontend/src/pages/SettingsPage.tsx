import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { useHealth } from "@/hooks/useHealth";
import { clearSession } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { clearServerUrl, isNative } from "@/lib/serverUrl";

export function SettingsPage() {
  // Purely informational — if /api/health hasn't answered yet (or is
  // unreachable), just show nothing rather than a loading/error state for
  // one line of fine print.
  const { data: health } = useHealth();

  return (
    <div className="space-y-5">
      <PreferencesCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
      {isNative() && (
        // Native-only: the web build always talks to its own same-origin
        // backend (see lib/serverUrl.ts), so there is nothing to change
        // there. No CardHeader/CardTitle here — mirrors PreferencesCard's
        // headerless layout since there's no separate section label for
        // this single action beyond the button text itself.
        <Card>
          <CardContent className="pt-4 sm:pt-5">
            <Button
              variant="secondary"
              onClick={() => {
                if (window.confirm(t("settings.changeServerConfirm"))) {
                  // Also end the current session — otherwise the OLD
                  // server's refresh token stays in localStorage and gets
                  // sent to whatever NEW host the user configures next
                  // (lib/auth.ts's bootstrap() has no way to know that
                  // token belongs to a different backend).
                  clearSession();
                  void clearServerUrl();
                }
              }}
            >
              {t("settings.changeServer")}
            </Button>
          </CardContent>
        </Card>
      )}
      {health?.version && (
        <p className="text-center text-xs text-text-muted">
          {t("settings.version", { version: health.version })}
        </p>
      )}
    </div>
  );
}
