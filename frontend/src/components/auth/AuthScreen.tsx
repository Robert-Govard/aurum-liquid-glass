import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { login, register, type AuthResult } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Mode = "login" | "register";
type Status = "idle" | "submitting" | AuthResult;

const ERROR_KEYS: Partial<Record<Status, string>> = {
  invalid: "auth.errorInvalidCredentials",
  email_taken: "auth.errorEmailTaken",
  error: "auth.errorGeneric",
  unreachable: "auth.errorUnreachable",
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
        </CardContent>
      </Card>
    </div>
  );
}
