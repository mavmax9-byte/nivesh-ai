import { apiClient, ApiError } from "@/lib/api-client";
import type {
  PlannedPortfolio,
  PlannedPortfolioJobStatus,
  PlannerRequest,
  RebalanceSuggestion,
} from "@/lib/api/types";

/** POST /planner/portfolios -- creates the portfolio row immediately
 * (status "generating") and enqueues the actual generation work. */
export function createPlannedPortfolio(
  payload: PlannerRequest,
): Promise<PlannedPortfolioJobStatus> {
  return apiClient.post<PlannedPortfolioJobStatus>("/planner/portfolios", payload);
}

/** GET /planner/portfolios/{id} -- always 200 with a `status` field
 * (generating/ready/failed), never 404 for an id that exists -- unlike
 * committee reports (keyed by symbol, legitimately absent until ever
 * run), a planned portfolio has a real job id from the moment it's
 * created. */
export function getPlannedPortfolio(id: string): Promise<PlannedPortfolio> {
  return apiClient.get<PlannedPortfolio>(`/planner/portfolios/${encodeURIComponent(id)}`);
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** "404 -> null" treatment matching pollCommitteeReport/pollSpecialistFinding
 * (lib/api/reports.ts) -- used only for a bad/unknown id, since a real
 * portfolio never 404s once created. */
export async function pollPlannedPortfolio(id: string): Promise<PlannedPortfolio | null> {
  try {
    return await getPlannedPortfolio(id);
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

/** GET /planner/portfolios/{id}/rebalance -- a v1.1 placeholder
 * (INVESTMENT_PLANNER_DESIGN.md §10); always returns `available: false`
 * today, but as a real, typed response rather than an error. */
export function getRebalanceSuggestion(id: string): Promise<RebalanceSuggestion> {
  return apiClient.get<RebalanceSuggestion>(
    `/planner/portfolios/${encodeURIComponent(id)}/rebalance`,
  );
}
