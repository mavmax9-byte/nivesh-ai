"""Fixed, versioned prompt templates for the Committee Chair.

Same fixed system + user message structure every specialist prompt uses
(`agents/fundamental/prompts.py` and its siblings), carrying the identical
hard rules (evidence-grounded, no advice language, JSON-only, cite-or-drop)
-- reused in spirit, not literally imported, since the Chair's rules are
phrased in terms of specialists' findings, not raw retrieved evidence
(INVESTMENT_COMMITTEE_DESIGN.md §6 point 3).

The user prompt presents each succeeded specialist's own summary +
domain-specific assessment + normalized findings (global citation indices,
see normalization.py), followed by the global citation list itself
(`citations.CommitteeCitationRef`, formatted the same
`[n] (type, date) title` shape `retrieval_engine.normalization.
build_context_text` already established for specialist prompts).
"""

from nivesh.ai_agents.committee.citations import CommitteeCitationRef
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.committee.normalization import NormalizedAssessment
from nivesh.ai_agents.models import (
    AGENT_CODE_FUNDAMENTAL_ANALYST,
    AGENT_CODE_NEWS_SENTIMENT_ANALYST,
    AGENT_CODE_RISK_ANALYST,
    AGENT_CODE_TECHNICAL_ANALYST,
    AGENT_CODE_VALUATION_ANALYST,
)

PROMPT_VERSION = "committee-chair-v1.1"

# Each specialist's own domain-specific narrative field, read straight out
# of its persisted result_json -- see each agent's own schemas.py.
_DOMAIN_FIELD_BY_AGENT_CODE: dict[str, str] = {
    AGENT_CODE_FUNDAMENTAL_ANALYST: "financial_health_assessment",
    AGENT_CODE_TECHNICAL_ANALYST: "technical_read",
    AGENT_CODE_VALUATION_ANALYST: "valuation_assessment",
    AGENT_CODE_NEWS_SENTIMENT_ANALYST: "sentiment_assessment",
    AGENT_CODE_RISK_ANALYST: "risk_assessment",
}

COMMITTEE_CHAIR_SYSTEM_PROMPT = """You are the Investment Committee Chair for an \
institutional-grade Indian equities research platform. Your job is to synthesize the findings \
of several specialist analysts -- who have already analyzed one company from different angles \
-- into one coherent, cited narrative, using ONLY the specialist findings and the global \
citation list provided in the user message.

Hard rules, no exceptions:
1. State only what the specialists' own findings support. Never introduce outside knowledge, \
training data, or your own independent analysis of the company. You are synthesizing, not \
re-analyzing.
2. Every observation in "findings" MUST cite at least one global citation index in \
"citation_refs". Never make an unsupported claim.
3. When specialists genuinely disagree (e.g. one is positive on a topic while another is \
negative), surface it explicitly in "disagreements" -- do NOT resolve it into a single \
verdict, a score, or an "on balance" statement. Only report a disagreement where the tension \
is real and specific, not a generic difference in domain focus.
4. You are producing RESEARCH, not ADVICE. Never recommend buying, selling, or holding a \
stock. Never state or imply a price target or portfolio allocation guidance, and never \
resolve the specialists' findings into anything resembling a recommendation.
5. "summary" MUST accurately reflect EVERY theme in "findings", including ones that conflict \
with each other. If findings point in different directions (e.g. positive news sentiment \
alongside a bearish technical signal), say so explicitly in "summary" -- never flatten a mixed \
picture into a single-direction narrative that omits or contradicts any finding. A specialist's \
own "Summary"/"Assessment" text given to you may itself be imprecise -- synthesize from its \
underlying findings, not just its prose.
6. Respond with JSON only, matching the exact schema provided. No prose outside the JSON.
7. "llm_confidence" (0.0-1.0) should reflect only how well-supported your synthesis is by the \
specialist findings actually given to you -- not general confidence about the company.
"""

_USER_PROMPT_INSTRUCTION = (
    "Synthesize the following specialist findings for {symbol} into one committee view. Cite "
    "every claim by its [n] global reference. Evidence not listed below does not exist for "
    "this synthesis.\n\n"
)


def _format_specialist_block(
    entry: SpecialistFindingInput, findings: list[NormalizedAssessment]
) -> str:
    lines = [
        f"--- {entry.agent_code} "
        f"(confidence={entry.confidence_score:.2f}, "
        f"evidence_sufficiency={entry.evidence_sufficiency}) ---",
        f"Summary: {entry.result_json.get('summary', '')}",
    ]
    domain_field = _DOMAIN_FIELD_BY_AGENT_CODE.get(entry.agent_code)
    if domain_field and entry.result_json.get(domain_field):
        lines.append(f"Assessment: {entry.result_json[domain_field]}")
    for finding in findings:
        if finding.agent_code != entry.agent_code:
            continue
        refs = ", ".join(f"[{idx}]" for idx in finding.citation_refs)
        lines.append(f"  - ({finding.stance}) {finding.metric}: {finding.observation} {refs}")
    return "\n".join(lines)


def _format_citation_block(global_citations: list[CommitteeCitationRef]) -> str:
    lines = ["Global citation list:"]
    for citation in global_citations:
        date_label = citation.evidence_date.isoformat() if citation.evidence_date else "undated"
        agents = ", ".join(citation.source_agent_codes)
        lines.append(
            f"[{citation.global_index}] ({citation.source_type}, {date_label}) "
            f"{citation.title} -- originally cited by: {agents}"
        )
    return "\n".join(lines)


def build_user_prompt(
    symbol: str,
    specialists: list[SpecialistFindingInput],
    findings: list[NormalizedAssessment],
    global_citations: list[CommitteeCitationRef],
) -> str:
    blocks = [_format_specialist_block(entry, findings) for entry in specialists]
    return (
        _USER_PROMPT_INSTRUCTION.format(symbol=symbol)
        + "\n\n".join(blocks)
        + "\n\n"
        + _format_citation_block(global_citations)
    )
