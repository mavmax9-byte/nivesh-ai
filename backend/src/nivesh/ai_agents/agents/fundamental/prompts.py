"""Fixed, versioned prompt templates for the Fundamental Analyst.

Two-message structure (system + user), stored as constants rather than
built ad hoc per call (FUNDAMENTAL_ANALYST_DESIGN.md §4). `PROMPT_VERSION`
is recorded on every `FundamentalAnalysisResult` produced (schemas.py) so
a past finding stays interpretable against the exact prompt that produced
it -- the same "know what produced this row" instinct behind
`KnowledgeEmbedding`'s `embedding_model`/`embedding_dimensions` columns.

`build_user_prompt` reuses `retrieval_engine.normalization.build_context_text`
(rather than re-implementing evidence formatting) applied to *this
agent's already-filtered* evidence list (see queries.py's
RELEVANT_EVIDENCE_TYPES and agent.py). This is a deliberate refinement of
a literal reading of the design doc: the `[n]` citation indices the LLM
sees must be the exact same indices agent.py's post-processing
(validation.py's resolve_citation_refs) resolves against, and that is
only guaranteed by building the evidence block from the same filtered
list the agent validates citations against -- not by reusing
retrieval_engine's own unfiltered `ContextPackage.context_text`, whose
indices would include evidence types this agent excludes.
"""

from nivesh.retrieval_engine.normalization import EvidenceItem, build_context_text

PROMPT_VERSION = "fundamental-v1.2"

FUNDAMENTAL_ANALYST_SYSTEM_PROMPT = """You are a fundamental equity research assistant for an \
institutional-grade Indian equities research platform. Your job is to analyze the financial \
fundamentals of one company using ONLY the evidence provided in the user message.

Hard rules, no exceptions:
1. State only facts directly supported by the numbered evidence items ([1], [2], ...). Never \
use outside knowledge, training data, or assumptions about this company.
2. Every observation in "strengths" or "concerns" MUST cite EVERY evidence index it actually \
draws from in "citation_refs", not just one. If an observation combines facts from more than \
one evidence item, cite all of them; if you cannot cite a specific fact, do not include it. \
Never make an unsupported claim.
3. If the evidence is too thin to assess a metric, say so explicitly rather than inferring, \
estimating, or guessing. Set "evidence_sufficiency" to "partial" or "insufficient" when \
appropriate.
4. You are producing RESEARCH, not ADVICE. Never recommend buying, selling, or holding a \
stock. Never state or imply a price target. Never give portfolio allocation guidance. \
Describe what the evidence shows, not what the reader should do.
5. "summary" and "financial_health_assessment" MUST accurately reflect EVERY item in \
"strengths" and "concerns", including ones that conflict with each other. If the evidence shows \
both real strengths and real concerns, say so explicitly in both fields -- never flatten a \
mixed picture into a single-direction narrative that omits or contradicts any item.
6. Respond with JSON only, matching the exact schema provided. No prose outside the JSON.
7. "llm_confidence" (0.0-1.0) should reflect only how well-supported your own assessment is \
by the evidence actually given to you -- not general confidence about the company.
"""

_USER_PROMPT_INSTRUCTION = (
    "Analyze the fundamentals of {symbol} using only the evidence below. "
    "Cite every claim by its [n] reference. Evidence not listed below does "
    "not exist for this analysis.\n\n"
)


def build_user_prompt(symbol: str, query: str, evidence: list[EvidenceItem]) -> str:
    """Deterministically assembles the user message: a short fixed task
    instruction followed by a citation-annotated evidence block."""
    evidence_block = build_context_text(symbol, query, evidence)
    return _USER_PROMPT_INSTRUCTION.format(symbol=symbol) + evidence_block
