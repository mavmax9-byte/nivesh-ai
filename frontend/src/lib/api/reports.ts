import { apiClient, ApiError } from "@/lib/api-client";
import type {
  AgentCode,
  AgentGenerationResponse,
  AnalysisJobStatus,
  CommitteeReport,
  SpecialistFinding,
  SpecialistMeta,
} from "@/lib/api/types";
import { SPECIALISTS } from "@/lib/api/types";

/** POST /reports -- enqueues a full Investment Committee run for a company. */
export function requestCommitteeReport(companyId: string): Promise<AnalysisJobStatus> {
  return apiClient.post<AnalysisJobStatus>("/reports", { company_id: companyId });
}

/** GET /reports/{symbol} -- the Chair's decision + Compliance verdict, read
 * together. 404s (via ApiError) if no decision exists yet, or the most
 * recent run was rejected by Compliance. */
export function getCommitteeReport(symbol: string): Promise<CommitteeReport> {
  return apiClient.get<CommitteeReport>(`/reports/${encodeURIComponent(symbol)}`);
}

/** POST /agents/{path}/{symbol} -- direct, standalone specialist invocation. */
export function generateSpecialistFinding(
  path: SpecialistMeta["path"],
  symbol: string,
): Promise<AgentGenerationResponse> {
  return apiClient.post<AgentGenerationResponse>(
    `/agents/${path}/${encodeURIComponent(symbol)}`,
  );
}

/** GET /agents/{path}/{symbol} -- most recently persisted finding for one
 * specialist. 404s (via ApiError) if none has ever been generated. */
export function getSpecialistFinding(
  path: SpecialistMeta["path"],
  symbol: string,
): Promise<SpecialistFinding> {
  return apiClient.get<SpecialistFinding>(`/agents/${path}/${encodeURIComponent(symbol)}`);
}

export interface SpecialistStatus {
  agentCode: AgentCode;
  path: SpecialistMeta["path"];
  finding: SpecialistFinding | null;
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** Treats "no finding yet" (404) as a plain `null`, not a thrown error --
 * the expected, common state while a committee run is still in progress.
 * Any other failure (network error, 500) still throws. */
export async function pollSpecialistFinding(
  path: SpecialistMeta["path"],
  symbol: string,
): Promise<SpecialistFinding | null> {
  try {
    return await getSpecialistFinding(path, symbol);
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

/** Same "404 -> null" treatment as pollSpecialistFinding, for the
 * committee decision itself (also covers "most recent run was rejected
 * by Compliance", which the API deliberately serves identically to
 * "never run" -- see backend ai_agents/router.py). */
export async function pollCommitteeReport(symbol: string): Promise<CommitteeReport | null> {
  try {
    return await getCommitteeReport(symbol);
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

export interface CommitteeProgressSnapshot {
  specialists: SpecialistStatus[];
  report: CommitteeReport | null;
}

/** One poll tick for the company hub's progress view: checks every
 * specialist's own persisted finding (for the live checklist) and the
 * committee decision itself (the actual completion signal), in parallel. */
export async function pollCommitteeProgress(symbol: string): Promise<CommitteeProgressSnapshot> {
  const [specialistResults, report] = await Promise.all([
    Promise.all(
      SPECIALISTS.map(async (s) => ({
        agentCode: s.agentCode,
        path: s.path,
        finding: await pollSpecialistFinding(s.path, symbol),
      })),
    ),
    pollCommitteeReport(symbol),
  ]);
  return { specialists: specialistResults, report };
}
