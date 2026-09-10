import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { setServerUrl } from "@/lib/serverUrl";
import { useTranslation } from "@/lib/i18n";

type Status = "idle" | "checking" | "invalid" | "unreachable";

/** Shown by ServerGate on native builds before anything else — a
 * self-hosted backend has no fixed address the app could ship with, so
 * the first thing a fresh native install needs is the user's own
 * server's URL. Verifies the address actually reaches a real Aurum
 * backend (via /api/health) before saving it via lib/serverUrl.ts's
 * setServerUrl(), so a typo shows an error immediately instead of
 * silently breaking every request afterward. */
export function ServerSetupScreen() {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    let origin: string;
    try {
      origin = new URL(url.trim()).origin;
    } catch {
      setStatus("invalid");
      return;
    }

    setStatus("checking");
    try {
      const response = await fetch(`${origin}/api/health`);
      if (!response.ok) {
        setStatus("unreachable");
        return;
      }
    } catch {
      setStatus("unreachable");
      return;
    }

    await setServerUrl(origin);
    // No further state update needed here — ServerGate re-renders
    // reactively the moment setServerUrl() changes lib/serverUrl.ts's
    // state, the same pattern AuthScreen relies on for login/register.
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
            <span className="text-xs text-text-muted">{t("serverSetup.subtitle")}</span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            <div>
              <Label htmlFor="server-url">{t("serverSetup.urlLabel")}</Label>
              <Input
                id="server-url"
                name="server-url"
                type="url"
                inputMode="url"
                autoCapitalize="none"
                autoCorrect="off"
                placeholder="https://aurum.example.com"
                autoFocus
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </div>

            {status === "invalid" && <p className="text-sm text-danger">{t("serverSetup.errorInvalidUrl")}</p>}
            {status === "unreachable" && <p className="text-sm text-danger">{t("serverSetup.errorUnreachable")}</p>}

            <Button type="submit" className="w-full" disabled={status === "checking"}>
              {status === "checking" ? t("serverSetup.checking") : t("serverSetup.continueButton")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
