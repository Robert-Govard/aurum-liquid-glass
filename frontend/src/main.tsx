import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { LoginGate } from "@/components/auth/LoginGate";
import { ServerGate } from "@/components/auth/ServerGate";
import { attachQueryClient } from "@/lib/auth";
import "@/lib/theme";
import "@/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

// Lets lib/auth.ts's clearSession() wipe this cache the moment a session
// ends (logout, or a failed token refresh) — otherwise a different user
// logging into the same tab afterward could briefly see the previous
// user's cached financial data (see lib/auth.ts's attachQueryClient docs).
attachQueryClient(queryClient);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ServerGate>
          <LoginGate>
            <App />
          </LoginGate>
        </ServerGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
