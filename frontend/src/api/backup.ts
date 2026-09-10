import { api } from "@/api/client";
import { getAccessToken, refreshAccessToken } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { getApiBase } from "@/lib/serverUrl";

export async function exportBackup(): Promise<void> {
  // Raw fetch (not api/client.ts's request()) — the response is a file
  // download, not JSON — so the Authorization header has to be attached
  // here by hand too, same as every other request. Uses the in-memory JWT
  // access token directly (see lib/auth.ts) rather than a Basic-Auth
  // header; this DOES get the same one-shot refresh-and-retry treatment
  // as api/client.ts's request() below, just implemented by hand since
  // request() itself can't be reused for a non-JSON file download.
  let accessToken = getAccessToken();
  let response = await fetch(`${getApiBase()}/backup/export`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (response.status === 401) {
    // The access token is missing or expired — try exactly once to
    // refresh it and replay this same request before giving up, same as
    // api/client.ts's request(). A still-401 result here is left for the
    // generic error handling below rather than clearing the session
    // ourselves — refreshAccessToken() already made the right call
    // internally (cleared for an invalid/expired token, or deliberately
    // left the session alone for a network failure).
    accessToken = await refreshAccessToken();
    if (accessToken) {
      response = await fetch(`${getApiBase()}/backup/export`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    }
  }
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const date = new Date().toISOString().slice(0, 10);

  const link = document.createElement("a");
  link.href = url;
  link.download = `aurum-backup-${date}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function importBackup(file: File): Promise<void> {
  const text = await file.text();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(t("backup.invalidFile"));
  }
  await api.post<{ status: string }>("/backup/import", payload);
}
