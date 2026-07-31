import { apiClient, ApiError } from "@/lib/api-client";
import type { ResearchDossier } from "@/lib/api/types";

export function getResearchDossier(symbol: string): Promise<ResearchDossier> {
  return apiClient.get<ResearchDossier>(`/research/${encodeURIComponent(symbol)}`);
}

/** Treats "no dossier synced yet" (404) as `null` -- a company can have a
 * committee report without ever having had a research dossier refresh,
 * since Investment Committee evidence comes from retrieval_engine
 * querying financials/technical/filings/news directly, not from the
 * research dossier itself. */
export async function pollResearchDossier(symbol: string): Promise<ResearchDossier | null> {
  try {
    return await getResearchDossier(symbol);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
