"""Compliance -- the final gate before a committee decision is publishable
(INVESTMENT_COMMITTEE_DESIGN.md §6/§9).

Not a `BaseAgent` -- it is a gate function over the Chair's already
citation-validated draft (`chair.py`), not a per-company evidence-consuming
specialist; it has no `retrieval_engine` query of its own and calls no LLM
(**deterministic-only**, confirmed during v1.0 planning -- no second,
nuanced LLM review pass is built for this version; revisit only once real
false negatives from the deterministic filter are actually observed in
production output).

Two checks, both re-verifications of guarantees the Chair's draft should
already satisfy, run here anyway as this platform's actual publish-time
gate rather than trusted implicitly:

1. **Investment-advice language.** The Chair's synthesized text is new
   LLM-generated text that was never checked by
   `guardrails.check_no_investment_advice` before now (unlike every
   specialist's own text, already checked once inside its own `agent.py`)
   -- this is the first and only time it is checked. Fail-closed, reusing
   v0.9's exact precedent: raises `InvestmentAdviceDetectedError`, not a
   silent strip.
2. **Citation traceability.** Every finding's and disagreement position's
   `citation_refs` must resolve within the draft's own global citation
   list. `chair.py` already guarantees this by construction (it drops
   anything out of range before returning), so this should always pass --
   verified explicitly anyway as the platform's actual audit point, not
   assumed true because another module says so.
"""

from dataclasses import dataclass

from nivesh.ai_agents.committee.schemas import CommitteeDecision
from nivesh.ai_agents.guardrails import InvestmentAdviceDetectedError, check_no_investment_advice


@dataclass(frozen=True)
class ComplianceVerdict:
    approved: bool
    reasons: list[str]


def review(decision: CommitteeDecision) -> ComplianceVerdict:
    reasons: list[str] = []

    try:
        check_no_investment_advice(
            decision.summary,
            *(finding.observation for finding in decision.findings),
            *(
                position.summary
                for disagreement in decision.disagreements
                for position in disagreement.positions
            ),
        )
    except InvestmentAdviceDetectedError as exc:
        reasons.append(f"Investment-advice language detected: {exc.message}")

    citation_count = len(decision.citations)
    untraceable = _find_untraceable_claims(decision, citation_count)
    if untraceable:
        reasons.append(
            f"{len(untraceable)} claim(s) cite a global reference outside the committee's own "
            f"citation list: {untraceable}."
        )

    return ComplianceVerdict(approved=not reasons, reasons=reasons)


def _find_untraceable_claims(decision: CommitteeDecision, citation_count: int) -> list[int]:
    bad_refs: set[int] = set()
    for finding in decision.findings:
        bad_refs.update(idx for idx in finding.citation_refs if not (1 <= idx <= citation_count))
    for disagreement in decision.disagreements:
        for position in disagreement.positions:
            bad_refs.update(
                idx for idx in position.citation_refs if not (1 <= idx <= citation_count)
            )
    return sorted(bad_refs)
