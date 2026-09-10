import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { bootstrap, useAuthState } from "@/lib/auth";

type Phase = "bootstrapping" | "ready";

/** Wraps the whole app. On mount, tries to turn a stored refresh token
 * (see lib/auth.ts) back into a live session — a fresh access token plus
 * the current user — before deciding what to render, so a page reload
 * doesn't flash the auth screen for an already-logged-in user. Once
 * bootstrapped, this is purely reactive: AuthScreen and the app swap
 * automatically whenever lib/auth.ts's session state changes (login,
 * register, logout, or a failed token refresh), no polling needed. */
export function LoginGate({ children }: { children: ReactNode }) {
  const { accessToken } = useAuthState();
  const [phase, setPhase] = useState<Phase>("bootstrapping");

  useEffect(() => {
    let cancelled = false;
    bootstrap().finally(() => {
      if (!cancelled) setPhase("ready");
    });
    return () => {
      cancelled = true;
    };
    // Deliberately runs once on mount only — later session changes are
    // handled by useAuthState() re-rendering this component directly, not
    // by re-running the bootstrap probe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (phase === "bootstrapping") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (!accessToken) {
    return <AuthScreen />;
  }

  return <>{children}</>;
}
