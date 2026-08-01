/**
 * TypeScript mirrors of the backend's Pydantic response schemas.
 *
 * Kept intentionally 1:1 with the Python shapes (see backend/src/nivesh/
 * companies/schemas.py, research/schemas.py, ai_agents/schemas.py,
 * ai_agents/guardrails.py, ai_agents/committee/schemas.py) so a backend
 * field rename is a compile error here, not a silent runtime mismatch --
 * this frontend has no data of its own, only what these endpoints return.
 */

// -- companies -----------------------------------------------------------

export interface Exchange {
  code: string;
  name: string;
}

export interface Company {
  id: string;
  symbol: string;
  name: string;
  exchange: Exchange;
  sector: string | null;
  industry: string | null;
  is_active: boolean;
}

// -- research dossier ------------------------------------------------------

export type SourceType =
  | "market_data"
  | "financial_data"
  | "corporate_action"
  | "corporate_filing"
  | "document_extraction"
  | "news"
  | "technical_indicator"
  | "knowledge_embedding"
  | "agent_finding";

export interface ResearchSnapshot {
  sector: string | null;
  industry: string | null;
  /** Pydantic serializes this Decimal field as a JSON string (e.g.
   * "2398.0000"), not a number -- parse with Number() before formatting. */
  latest_price: string | null;
  latest_trade_date: string | null;
  price_bar_count: number;
  price_history_start: string | null;
  price_history_end: string | null;
  corporate_action_count: number;
  latest_corporate_action_date: string | null;
}

export interface ResearchVersion {
  version_number: number;
  triggered_by: string;
  change_summary: string;
  created_at: string;
  snapshot: ResearchSnapshot | null;
}

export interface ResearchTimelineEvent {
  event_type: string;
  description: string;
  event_timestamp: string;
}

export interface ResearchEvidenceSummary {
  source_type: SourceType;
  record_count: number;
}

export interface ResearchDossier {
  symbol: string;
  current_version_number: number;
  last_refreshed_at: string | null;
  latest_version: ResearchVersion | null;
  recent_timeline: ResearchTimelineEvent[];
  evidence_summary: ResearchEvidenceSummary[];
}

// -- ai_agents: shared shapes ----------------------------------------------

export type Stance = "positive" | "negative" | "neutral";
export type EvidenceSufficiency = "sufficient" | "partial" | "insufficient";

export interface CitationRef {
  index: number;
  source_type: string;
  source_table: string;
  source_id: string;
  title: string;
  evidence_date: string | null;
}

export interface SpecialistAssessment {
  metric: string;
  observation: string;
  stance: Stance;
  citation_refs: number[];
}

export interface FundamentalMetricAssessment {
  metric: string;
  observation: string;
  citation_refs: number[];
}

export interface AgentGenerationResponse {
  symbol: string;
  status: string;
  task_id: string;
}

export interface AnalysisJobStatus {
  job_id: string;
  status: string;
}

// -- ai_agents: specialist findings -----------------------------------------

export type AgentCode =
  | "fundamental_analyst"
  | "technical_analyst"
  | "valuation_analyst"
  | "news_sentiment_analyst"
  | "risk_analyst";

interface SpecialistResultBase {
  company_symbol: string;
  summary: string;
  evidence_sufficiency: EvidenceSufficiency;
  confidence_score: number;
  citations: CitationRef[];
  caveats: string[];
  prompt_version: string;
  model_used: string;
  generated_at: string;
}

/** result_json for agent_code === "fundamental_analyst" */
export interface FundamentalResultJson extends SpecialistResultBase {
  strengths: FundamentalMetricAssessment[];
  concerns: FundamentalMetricAssessment[];
  financial_health_assessment: string;
}

/** result_json for every other (v1.0) specialist -- one shared shape,
 * differing only in which domain-specific narrative field is present. */
export interface GenericSpecialistResultJson extends SpecialistResultBase {
  findings: SpecialistAssessment[];
  technical_read?: string;
  valuation_assessment?: string;
  sentiment_assessment?: string;
  risk_assessment?: string;
}

export type SpecialistResultJson = FundamentalResultJson | GenericSpecialistResultJson;

export function isFundamentalResult(
  result: SpecialistResultJson,
): result is FundamentalResultJson {
  return "strengths" in result;
}

export interface SpecialistFinding {
  id: string;
  company_id: string;
  agent_code: AgentCode;
  result_json: SpecialistResultJson;
  prompt_version: string;
  model_used: string;
  confidence_score: number;
  evidence_sufficiency: EvidenceSufficiency;
  created_at: string;
  updated_at: string;
}

// -- ai_agents: committee ----------------------------------------------------

export interface CommitteeCitationRef {
  global_index: number;
  source_agent_codes: string[];
  source_type: string;
  source_table: string;
  source_id: string;
  title: string;
  evidence_date: string | null;
}

export interface CommitteeThemeFinding {
  theme: string;
  observation: string;
  stance: Stance;
  citation_refs: number[];
}

export interface DisagreementPosition {
  agent_code: string;
  stance: Stance;
  summary: string;
  citation_refs: number[];
}

export interface AgentDisagreement {
  topic: string;
  positions: DisagreementPosition[];
}

export interface SourceFindingRef {
  agent_code: string;
  finding_id: string;
  confidence_score: number;
  evidence_sufficiency: EvidenceSufficiency;
}

/** result_json inside CommitteeReportRead -- CommitteeDecision plus the
 * orchestrator's own aggregated evidence_sufficiency (merged in at
 * persist time, not part of the Chair's own schema). */
export interface CommitteeDecisionJson {
  company_symbol: string;
  summary: string;
  findings: CommitteeThemeFinding[];
  disagreements: AgentDisagreement[];
  confidence_score: number;
  citations: CommitteeCitationRef[];
  caveats: string[];
  source_findings: SourceFindingRef[];
  failed_specialists: string[];
  evidence_sufficiency: EvidenceSufficiency;
  prompt_version: string;
  model_used: string;
  generated_at: string;
}

export interface ComplianceVerdictJson {
  approved: boolean;
  reasons: string[];
  evidence_sufficiency: EvidenceSufficiency;
}

export interface CommitteeReport {
  company_id: string;
  company_symbol: string;
  result_json: CommitteeDecisionJson;
  compliance: ComplianceVerdictJson;
  confidence_score: number;
  created_at: string;
  updated_at: string;
}

// -- specialist metadata (frontend-only convenience) -------------------------

export interface SpecialistMeta {
  agentCode: AgentCode;
  /** URL path segment, matches both the backend route (/agents/<path>/...)
   * and this app's own /specialists/<path> route. */
  path: "fundamental" | "technical" | "valuation" | "news-sentiment" | "risk";
  label: string;
  shortLabel: string;
  description: string;
  domainField: keyof GenericSpecialistResultJson | "financial_health_assessment";
}

export const SPECIALISTS: readonly SpecialistMeta[] = [
  {
    agentCode: "fundamental_analyst",
    path: "fundamental",
    label: "Fundamental Analyst",
    shortLabel: "Fundamental",
    description: "Financial statements, profitability, margins, and balance sheet strength.",
    domainField: "financial_health_assessment",
  },
  {
    agentCode: "technical_analyst",
    path: "technical",
    label: "Technical Analyst",
    shortLabel: "Technical",
    description: "Trend, momentum, volatility, and volume from technical indicators.",
    domainField: "technical_read",
  },
  {
    agentCode: "valuation_analyst",
    path: "valuation",
    label: "Valuation Analyst",
    shortLabel: "Valuation",
    description: "Whether fundamentals are reasonably reflected in valuation.",
    domainField: "valuation_assessment",
  },
  {
    agentCode: "news_sentiment_analyst",
    path: "news-sentiment",
    label: "News & Sentiment Analyst",
    shortLabel: "News & Sentiment",
    description: "Tone and substance of recent news coverage and disclosures.",
    domainField: "sentiment_assessment",
  },
  {
    agentCode: "risk_analyst",
    path: "risk",
    label: "Risk Analyst",
    shortLabel: "Risk",
    description: "Disclosed and inferable leverage, liquidity, and risk factors.",
    domainField: "risk_assessment",
  },
] as const;

export function specialistMeta(path: string): SpecialistMeta | undefined {
  return SPECIALISTS.find((s) => s.path === path);
}

export function domainNarrative(result: SpecialistResultJson, meta: SpecialistMeta): string {
  if (isFundamentalResult(result)) return result.financial_health_assessment;
  const generic = result as GenericSpecialistResultJson;
  const value = generic[meta.domainField as keyof GenericSpecialistResultJson];
  return typeof value === "string" ? value : "";
}

// -- citation lookups (frontend-only convenience) ----------------------------

export interface CitationLookupEntry {
  title: string;
  sourceType: string;
  evidenceDate: string | null;
}

export function citationLookupFromSpecialist(
  citations: CitationRef[],
): Map<number, CitationLookupEntry> {
  return new Map(
    citations.map((c) => [
      c.index,
      { title: c.title, sourceType: c.source_type, evidenceDate: c.evidence_date },
    ]),
  );
}

export function citationLookupFromCommittee(
  citations: CommitteeCitationRef[],
): Map<number, CitationLookupEntry> {
  return new Map(
    citations.map((c) => [
      c.global_index,
      { title: c.title, sourceType: c.source_type, evidenceDate: c.evidence_date },
    ]),
  );
}

const ACRONYMS = new Set(["pe", "pb", "roe", "roa", "eps", "yoy", "qoq", "cagr", "ebitda"]);

/** "pe_ratio" -> "PE Ratio", "revenue_growth" -> "Revenue Growth" -- plain
 * Title Case via CSS `capitalize` reads oddly for finance acronyms (e.g.
 * "Pe Ratio"), so short known tokens are upper-cased instead. */
export function formatMetricLabel(metric: string): string {
  return metric
    .split("_")
    .map((word) => (ACRONYMS.has(word.toLowerCase()) ? word.toUpperCase() : word))
    .join(" ")
    .replace(/(^|\s)([a-z])/g, (_, boundary, letter) => `${boundary}${letter.toUpperCase()}`);
}

export function specialistAssessments(
  result: SpecialistResultJson,
): { metric: string; observation: string; stance: Stance; citation_refs: number[] }[] {
  if (isFundamentalResult(result)) {
    return [
      ...result.strengths.map((a) => ({ ...a, stance: "positive" as Stance })),
      ...result.concerns.map((a) => ({ ...a, stance: "negative" as Stance })),
    ];
  }
  return result.findings;
}

// ---------------------------------------------------------------------
// Portfolio Planner (INVESTMENT_PLANNER_DESIGN.md) -- mirrors
// backend/src/nivesh/portfolio_planner/schemas.py 1:1, the same
// "compile error over silent mismatch" discipline every other type in
// this file follows.
// ---------------------------------------------------------------------

export type RiskProfile = "conservative" | "balanced" | "growth";
export type Horizon = "short" | "medium" | "long";
export type PlannerPortfolioStatus = "generating" | "ready" | "failed";

export interface PlannerRequest {
  capital: number;
  risk_profile: RiskProfile;
  horizon: Horizon;
  sector_exclusions?: string[];
}

export interface PlannedPortfolioJobStatus {
  id: string;
  status: PlannerPortfolioStatus;
}

export interface PlannedHolding {
  company_id: string;
  symbol: string;
  company_name: string;
  sector: string | null;
  allocated_amount: number;
  allocated_weight: number;
  rank_score: number;
  confidence_score: number;
  evidence_sufficiency: EvidenceSufficiency;
  thesis: string;
  weight_rationale: string;
  top_citation_title: string | null;
  top_citation_source_type: string | null;
}

export interface PlannedPortfolio {
  id: string;
  capital: number;
  risk_profile: RiskProfile;
  horizon: Horizon;
  sector_exclusions: string[];
  status: PlannerPortfolioStatus;
  summary: string | null;
  caveats: string[];
  unallocated_amount: number | null;
  confidence_score: number | null;
  evidence_sufficiency: EvidenceSufficiency | null;
  universe_size: number | null;
  failure_reason: string | null;
  holdings: PlannedHolding[];
  created_at: string;
  updated_at: string;
}

export interface RebalanceSuggestion {
  available: boolean;
  message: string;
}

export const RISK_PROFILES: { value: RiskProfile; label: string; description: string }[] = [
  {
    value: "conservative",
    label: "Conservative",
    description: "Favors well-evidenced, lower-volatility holdings and diversifies more tightly.",
  },
  {
    value: "balanced",
    label: "Balanced",
    description: "An even mix of stability and growth, weighted toward higher-confidence research.",
  },
  {
    value: "growth",
    label: "Growth",
    description: "Willing to concentrate more in higher-momentum names for higher upside.",
  },
];

export const HORIZONS: { value: Horizon; label: string }[] = [
  { value: "short", label: "Short-term (under 1 year)" },
  { value: "medium", label: "Medium-term (1–3 years)" },
  { value: "long", label: "Long-term (3+ years)" },
];
