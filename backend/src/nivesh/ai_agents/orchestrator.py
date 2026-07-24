"""Investment Committee orchestrator (placeholder).

Per docs/v2 05-Investment-Committee.md, the real orchestrator aggregates
Findings Store entries, detects conflicts, applies weighted scoring, runs
the LLM synthesis step, and passes the draft through the Compliance Agent
before publication. None of that is implemented here -- this stub exists so
the API layer, task queue, and future agent implementations have a stable
integration point.
"""

import logging
import uuid

from nivesh.core.exceptions import NotImplementedYetError

logger = logging.getLogger(__name__)


class InvestmentCommitteeOrchestrator:
    async def request_analysis(self, company_id: uuid.UUID) -> uuid.UUID:
        """Enqueue a research cycle for a company and return a job id.

        TODO: dispatch specialist agents via Celery, aggregate findings,
        and run the Investment Committee process (docs/v2 05).
        """
        logger.info("analysis_requested_placeholder", extra={"company_id": str(company_id)})
        raise NotImplementedYetError(
            "AI-driven analysis is not implemented in this scaffold.",
            details={"company_id": str(company_id)},
        )
