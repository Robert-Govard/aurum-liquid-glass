import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { Card, CardContent } from "@/components/ui/Card";
import { verifyEmail } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Status = "verifying" | "success" | "error";

/** Rendered by LoginGate instead of AuthScreen when there's no session and
 * the current path is /verify-email — the destination of the link sent by
 * the backend's email_service.py. Reads the token from the query string
 * and spends it via lib/auth.ts's verifyEmail(); on success that function
 * updates the shared session state itself, so LoginGate reactively swaps
 * to rendering the app the moment this resolves — this screen only ever
 * needs to show progress or failure, never navigate anywhere on success. */
export function VerifyEmailScreen() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<Status>("verifying");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      return;
    }
    let cancelled = false;
    void verifyEmail(token).then((result) => {
      if (!cancelled) setStatus(result === "ok" ? "success" : "error");
    });
    return () => {
      cancelled = true;
    };
    // Deliberately runs once on mount only — the token in the URL never changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-4 p-6 pt-8 text-center sm:p-8">
          <Logo size={40} />
          <p className="text-sm text-text-secondary">
            {status === "verifying" && t("auth.verifying")}
            {status === "success" && t("auth.verifySuccess")}
            {status === "error" && t("auth.verifyError")}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
