"""Committee Chair synthesis pipeline (INVESTMENT_COMMITTEE_DESIGN.md §6).

Not a `BaseAgent` -- the Chair never calls `retrieval_engine` directly; its
only inputs are succeeded specialists' own already-persisted findings
(`SpecialistFindingInput`, passed in by the orchestrator). This module owns
steps 1-5 of the synthesis pipeline: build the global citation list (§7),
normalize specialist findings onto it, assemble the prompt, call the LLM,
and apply the citation-range guardrail to the Chair's own output. Step 6
(Compliance) is a separate gate the orchestrator applies afterward
(committee/compliance.py) -- the Chair's output is a validated draft, not
yet a publishable committee decision.

**The investment-advice-language check is deliberately NOT run here.**
Per §6: "the Chair's output is new LLM-generated text that hasn't been
checked yet" -- that check is Compliance's job specifically (§6/§9), the
final gate before anything is treated as publishable, not duplicated at
this layer. Citation-range validation *is* done here, same as every
specialist -- it is what makes this draft's own claims well-formed, not a
compliance concern per se.
"""

import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from nivesh.ai_agents.committee.citations import build_global_citations
from nivesh.ai_agents.committee.confidence import compute_committee_confidence
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.committee.normalization import normalize_findings
from nivesh.ai_agents.committee.prompts import (
    COMMITTEE_CHAIR_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_user_prompt,
)
from nivesh.ai_agents.committee.schemas import (
    AgentDisagreement,
    CommitteeDecision,
    LLMCommitteeOutput,
    SourceFindingRef,
)
from nivesh.ai_agents.guardrails import drop_unsupported_assessments
from nivesh.ai_agents.providers.base import LLMProvider
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError

logger = logging.getLogger(__name__)


class CommitteeChair:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def synthesize(
        self,
        symbol: str,
        succeeded_specialists: list[SpecialistFindingInput],
        failed_specialists: list[str],
    ) -> CommitteeDecision:
        """`succeeded_specialists` must be non-empty -- the orchestrator is
        responsible for the zero-successes and quorum checks (§9) before
        ever calling this."""
        global_citations, local_to_global = build_global_citations(succeeded_specialists)
        normalized_findings = normalize_findings(succeeded_specialists, local_to_global)

        user_prompt = build_user_prompt(
            symbol, succeeded_specialists, normalized_findings, global_citations
        )
        completion = await self._llm.complete(
            COMMITTEE_CHAIR_SYSTEM_PROMPT,
            user_prompt,
            LLMCommitteeOutput.model_json_schema(),
        )

        try:
            llm_output = LLMCommitteeOutput.model_validate(completion.parsed_json)
        except ValidationError as exc:
            raise LLMResponseParsingError(
                f"Committee Chair LLM response did not match the expected schema: {exc}"
            ) from exc

        citation_count = len(global_citations)
        findings, dropped_findings = drop_unsupported_assessments(
            llm_output.findings, citation_count
        )
        disagreements, dropped_positions = self._validate_disagreements(
            llm_output.disagreements, citation_count
        )

        confidence_score = compute_committee_confidence(
            succeeded_specialists, llm_output.llm_confidence
        )

        caveats: list[str] = []
        dropped_total = dropped_findings + dropped_positions
        if dropped_total:
            caveats.append(
                f"{dropped_total} claim(s) were removed for citing evidence outside the "
                f"provided global reference list."
            )
        if failed_specialists:
            caveats.append(
                f"The following specialists did not contribute to this synthesis (their run "
                f"failed): {', '.join(failed_specialists)}."
            )

        return CommitteeDecision(
            company_symbol=symbol,
            summary=llm_output.summary,
            findings=findings,
            disagreements=disagreements,
            confidence_score=confidence_score,
            citations=global_citations,
            caveats=caveats,
            source_findings=[
                SourceFindingRef(
                    agent_code=entry.agent_code,
                    finding_id=entry.finding_id,
                    confidence_score=entry.confidence_score,
                    evidence_sufficiency=entry.evidence_sufficiency,
                )
                for entry in succeeded_specialists
            ],
            failed_specialists=failed_specialists,
            prompt_version=PROMPT_VERSION,
            model_used=completion.model,
            generated_at=datetime.now(UTC),
        )

    # -- internals -----------------------------------------------------

    @staticmethod
    def _validate_disagreements(
        disagreements: list[AgentDisagreement], citation_count: int
    ) -> tuple[list[AgentDisagreement], int]:
        """Citation enforcement applies to disagreements too (§5/§7/§9):
        each disagreement's positions are individually range-validated and
        unsupported-claim-dropped via the shared guardrail, and a
        disagreement left with zero surviving positions is dropped
        entirely -- a disagreement with nothing left to say is not a
        disagreement."""
        kept: list[AgentDisagreement] = []
        total_dropped = 0
        for disagreement in disagreements:
            positions, dropped = drop_unsupported_assessments(
                disagreement.positions, citation_count
            )
            total_dropped += dropped
            if positions:
                kept.append(disagreement.model_copy(update={"positions": positions}))
        return kept, total_dropped
