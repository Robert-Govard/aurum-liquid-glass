import { type ReactNode, useEffect } from "react";
import { Logo } from "@/components/layout/Logo";
import { ServerSetupScreen } from "@/components/auth/ServerSetupScreen";
import { bootstrapServerUrl, isNative, useServerState } from "@/lib/serverUrl";

/** Wraps LoginGate/App, outermost — must resolve before anything else,
 * since even LoginGate's own session bootstrap makes an API call. On the
 * web this is a pure passthrough: `isNative()` is false, there's always a
 * same-origin nginx proxy at /api, and nothing here ever blocks
 * rendering. Only on a native build does this show ServerSetupScreen
 * until a backend address has been configured (see lib/serverUrl.ts). */
export function ServerGate({ children }: { children: ReactNode }) {
  const { ready, serverUrl } = useServerState();

  useEffect(() => {
    bootstrapServerUrl();
    // Deliberately runs once on mount only — later changes are handled by
    // useServerState() re-rendering this component directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (isNative() && !serverUrl) {
    return <ServerSetupScreen />;
  }

  return <>{children}</>;
}
