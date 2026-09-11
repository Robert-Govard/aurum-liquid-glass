import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { clearSession, login, register, type AuthResult } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";
import { clearServerUrl, isNative } from "@/lib/serverUrl";

type Mode = "login" | "register";
type Status = "idle" | "submitting" | AuthResult;

const ERROR_KEYS: Partial<Record<Status, string>> = {
  invalid: "auth.errorInvalidCredentials",
  email_taken: "auth.errorEmailTaken",
  error: "auth.errorGeneric",
  unreachable: "auth.errorUnreachable",
  email_not_verified: "auth.errorEmailNotVerified",
};

/** Shown by LoginGate whenever there's no live session — collects an
 * email/password and either signs in or creates a new account (see
 * lib/auth.ts's login()/register()), which is what actually establishes
 * the session every subsequent request authenticates with. On success
 * this component doesn't navigate anywhere itself — LoginGate's
 * useAuthState() reactively swaps to rendering the app the moment
 * lib/auth.ts's session state changes, so this just stops being rendered. */
export function AuthScreen() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("submitting");
    const result = await (mode === "login" ? login(email, password) : register(email, password));
    setStatus(result);
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setStatus("idle");
  };

  const errorKey = ERROR_KEYS[status];

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
            <span className="text-xs text-text-muted">{t("auth.subtitle")}</span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            <div>
              <Label htmlFor="auth-email">{t("auth.emailLabel")}</Label>
              <Input
                id="auth-email"
                name="email"
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="auth-password">{t("auth.passwordLabel")}</Label>
              <Input
                id="auth-password"
                name="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {mode === "register" && <p className="mt-1 text-xs text-text-muted">{t("auth.passwordHint")}</p>}
            </div>

            {status === "verify_email_sent" && (
              <p className="text-sm text-text-secondary">{t("auth.verifyEmailSent")}</p>
            )}
            {errorKey && <p className="text-sm text-danger">{t(errorKey as Parameters<typeof t>[0])}</p>}

            <Button type="submit" className="w-full" disabled={status === "submitting"}>
              {status === "submitting"
                ? t(mode === "login" ? "auth.submitting" : "auth.registering")
                : t(mode === "login" ? "auth.submitButton" : "auth.registerButton")}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => switchMode(mode === "login" ? "register" : "login")}
            className="text-xs text-text-secondary underline-offset-2 hover:underline"
          >
            {t(mode === "login" ? "auth.switchToRegister" : "auth.switchToLogin")}
          </button>

          {status === "email_not_verified" && (
            <button
              type="button"
              onClick={async () => {
                setStatus("submitting");
                setStatus(await register(email, password));
              }}
              className="text-xs text-text-secondary underline-offset-2 hover:underline"
            >
              {t("auth.resendVerification")}
            </button>
          )}

          {isNative() && (
            // Native-only escape hatch: Settings (where "change server"
            // normally lives) is only reachable after a successful login,
            // but a self-hoster whose backend address changed (e.g. a home
            // LAN IP) would otherwise be stuck failing to log in against
            // the old, now-wrong address with no way back to
            // ServerSetupScreen short of clearing app data. clearSession()
            // is harmless/idempotent here — there is no live session yet
            // at this screen — but is called anyway for the same reason
            // as Settings' version: keep the "always clear both together"
            // invariant so a stale token can never survive a server change.
            <button
              type="button"
              onClick={() => {
                if (window.confirm(t("settings.changeServerConfirm"))) {
                  clearSession();
                  void clearServerUrl();
                }
              }}
              className="text-xs text-text-secondary underline-offset-2 hover:underline"
            >
              {t("auth.changeServer")}
            </button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
