# AI Investment Planner — Product Design Document (v1.1... "1.1" as a product-layer label, distinct from the frontend v1.1)

**Status:** CONFIRMED — design phase complete per explicit user instruction.
This document is the source of truth for implementation, read alongside
PROJECT_CONTEXT.md. Do not redesign against this document without an
explicit conversation with the user first, the same rhythm every prior
version followed (PROJECT_CONTEXT.md §15 point 3).

**Author context:** produced during a design-only session (no code
written), then confirmed by the user as final and handed back for
implementation. The goal: transform the existing single-company research
platform into a product that answers *"I have ₹X. Where should I invest
and why?"* for a **retail investor**, not an equity research analyst.

---

## 0. Framing: the one constraint every section below is built around

The existing platform's identity is explicitly "research only, never
advice" — `Compliance` hard-fails any buy/sell/hold language, and
PROJECT_CONTEXT.md §1/§13 treat this as non-negotiable. A planner that
says *"invest ₹X here"* sits right at that line — in India, personalized
investment recommendations are SEBI-regulated (Registered Investment
Advisor) territory. This does not block the design, but shapes it
throughout: everything is framed as an **illustrative, evidence-cited
allocation for the user to evaluate**, never as a directive.

**The single most important architectural principle**: the planner is a
**deterministic aggregation/ranking/allocation layer over already-
guardrailed Investment Committee output** — not a new LLM call that
free-reasons "buy X." It reuses the backend's existing guardrails
(citation enforcement, no-advice-language filter, confidence flooring,
Compliance gate) instead of opening a second, ungrounded surface for the
same risks the existing system already solved once. No new AI agent is
introduced by this document.

---

## 1. User journey

1. **State capital & preferences** — one short screen, not a
   questionnaire.
2. **System proposes a portfolio** — N holdings, ₹ allocations, one-line
   "why" each.
3. **Review screen** — skim-first (visual allocation, plain-language
   reasons); drill into any holding for the *existing* full Investment
   Committee report for analyst depth.
4. **Adjust or accept** — change risk profile/exclusions and regenerate,
   or save the plan.
5. **Periodic return** — the app surfaces a rebalancing suggestion when
   something material changes; user reviews and decides, nothing moves on
   its own.

## 2. Inputs required

| Input | Required | Notes |
|---|---|---|
| Investable amount (₹) | Yes | Numeric only |
| Risk tolerance | Yes | 3 cards: Conservative / Balanced / Growth |
| Horizon | Yes | Short (<1y) / Medium (1–3y) / Long (3y+) |
| Sector exclusions | No | From existing `companies.sector`/`industry` values |
| Existing holdings | No | Deferred to a future version — v1.1 plans from scratch |

No KYC, no bank linkage, no suitability questionnaire beyond the three
required fields.

## 3. Portfolio generation workflow

1. **Universe selection** (§4) — narrow all companies to a candidate set.
2. **Freshness check** — reuse `GET /reports/{symbol}`; if missing/stale,
   queue `POST /reports` (existing endpoints, unchanged).
3. **Ranking** (§5) — deterministic composite score over each candidate's
   existing committee output.
4. **Risk-profile filtering** (§6/7).
5. **Allocation** (§6) — position sizing with diversification caps.
6. **Explanation generation** (§8) — templated compression of each
   committee's own `summary`/citations. No new LLM reasoning.
7. **Portfolio Review screen** (§9).

## 4. Universe selection strategy

Two-tier funnel (a full committee report costs 5–6 real LLM calls; the
entire company table cannot be screened that way):

- **Tier 1 (free, deterministic)**: `is_active` companies with synced
  `financial_statements` (mirrors Fundamental's own quorum requirement),
  matching sector exclusions.
- **Tier 2 (free, deterministic)**: pre-rank survivors using data already
  computed (latest technical snapshot, existing ratios) to shortlist
  candidates worth a real committee run.
- **Tier 3 (expensive)**: only the shortlist gets a fresh/full Investment
  Committee report.

**v1.1 sandbox note**: this project's real dev/demo data covers a small
number of seeded companies (TCS, confirmed rich). The universe-selection
code must work correctly for an arbitrarily small candidate pool — it is
not allowed to assume N is large.

## 5. Ranking methodology

Weighted composite over fields the Committee already produces:

- `confidence_score` (0–1)
- `evidence_sufficiency` (sufficient > partial > insufficient)
- Specialist stance tally (positive vs. negative across the 5 specialists)
- Disagreement count/severity (more disagreement → smaller position, not
  automatic exclusion)
- **Hard filter**: `compliance.approved=true` only
- Valuation sanity: existing P/E percentile vs. candidate set

Weights shift by risk profile (Growth weights Technical higher;
Conservative weights Fundamental/Risk higher).

## 6. Allocation strategy

- Target as many holdings as the candidate universe and capital support;
  never force diversification the real data can't back.
- Max single-position cap (e.g., 20%) regardless of score.
- Max sector cap (e.g., ~35%), using existing `sector` field.
- Default: score-weighted within caps.
- Round to sensible ₹ amounts; show unallocated residual explicitly
  rather than forcing a fit to 100%.

## 7. Risk management

- Concentration caps are hard-coded, not LLM-decided.
- Never include a holding with `compliance.approved=false` or a
  stale/missing report.
- Risk-profile-driven exclusion (Conservative drops negative/insufficient
  Risk-specialist stances).
- Portfolio-level evidence-sufficiency badge = worst-of across holdings.
- Persistent, non-dismissable disclaimer: illustrative, evidence-cited
  allocation, not personalized investment advice.

## 8. Explanation format

Per holding, templated from the existing committee's own output:

- One-line thesis (compressed from committee `summary`).
- Confidence + evidence-sufficiency badges (reuse existing components).
- "Why this weight" — one line tying score/confidence to position size.
- Link to the existing, unmodified full report/specialists/evidence pages.

## 9. Portfolio review screen

- Header: capital, holding count, aggregate confidence/evidence badges,
  generation date.
- Visual allocation (by holding and by sector).
- Holdings list: ticker, ₹/%, one-line why, confidence badge, link out.
- Caveats/disagreements section, shown honestly.
- Persistent disclaimer banner.
- Actions: Regenerate · Save plan · View rebalancing suggestion.

## 10. Rebalancing strategy

**v1.1 scope: placeholder only.** The review screen and API surface a
"Rebalancing" entry point and a clear, honest "not yet available" state
— no drift/time/evidence-change triggers are implemented this version.
Building the real triggers needs live portfolios accumulating real
drift/staleness history over time, which does not exist yet the moment
this version ships. This is a deliberate scope cut, not an oversight —
see §12 (Roadmap) in PROJECT_CONTEXT.md once this version's own entry is
added there.

## 11. API design

New, additive endpoints; nothing existing changes:

```
POST /planner/portfolios
  {capital, risk_profile, horizon, sector_exclusions?}
  -> 202 {job_id, status: "queued"}

GET  /planner/portfolios/{id}
  -> the generated portfolio (holdings, allocations, explanations, badges)
  -> 404 if not ready yet

GET  /planner/portfolios/{id}/rebalance
  -> 501/placeholder response for v1.1 (see §10)
```

New `portfolio_planner` backend module, same shape every domain module
follows (models/repository/service/schemas/router), reading only from
`ai_agents`/`companies`/`retrieval_engine`/`research` — it does not
modify them.

## 12. UI flow

Reuses the existing design system entirely (`Badge`, `ConfidenceMeter`,
`StanceBadge`, `CitationRefs`, `PageHeader`) — no new visual language.

1. "Build my portfolio" CTA alongside "Search a company" on the landing
   page.
2. Input screen: capital, risk-profile cards, horizon, optional
   exclusions.
3. Generating screen: reuses the existing `usePolling` progress-checklist
   pattern.
4. Portfolio Review screen (§9).
5. Drill-down to the existing, unmodified `/companies/{symbol}` pages.
6. Rebalancing screen: placeholder state (§10).
