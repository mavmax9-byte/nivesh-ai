"""Specialist agent contract.

Per docs/v2 04-Multi-Agent-Research-System.md, every specialist agent
(Market Data, Financial Analysis, Technical Analysis, Valuation, News
Intelligence, Macro Economy, Risk Analysis, Portfolio Analysis, Compliance)
implements this interface and writes its output to the Findings Store,
never directly to another agent.

`AgentFinding.detail` was added in v0.9 (additive, backward compatible --
see FUNDAMENTAL_ANALYST_DESIGN.md §6/§12) so a concrete agent can carry
its own richer structured result (e.g. `FundamentalAnalysisResult`,
serialized) alongside the common summary/confidence/evidence_ids envelope
every future agent and a future Investment Committee orchestrator can
still rely on uniformly. `agents/fundamental/agent.py` is the first real
implementation of this contract; every other agent named above remains
unimplemented.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentContext:
    """Everything a specialist agent needs to run once, for one company."""

    company_id: str
    trigger_type: str
    prior_finding: dict[str, Any] | None = None


@dataclass
class AgentFinding:
    """The structured shape every agent writes to the Findings Store."""

    agent_code: str
    summary: str
    confidence_score: float
    evidence_ids: list[str]
    detail: dict[str, Any] | None = None


class BaseAgent(ABC):
    agent_code: str

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentFinding:
        """Execute one analysis pass and return a structured finding.

        Real implementations call scoped Knowledge Layer tools only (per
        docs/v2 03-Knowledge-Layer.md) -- never raw ingestion tables.
        """
        raise NotImplementedError
