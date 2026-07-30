"""ai_agents data-access layer.

`AgentFindingRepository` owns its own table (unlike `retrieval_engine`'s
`RetrievalRepository`, which owns none) -- one row per `(company_id,
agent_code)`, upserted in place. `upsert` commits its own write directly
(mirroring `TechnicalIndicatorRepository.bulk_upsert`'s "every value here
is a pure recomputation" reasoning -- a finding is the output of a fresh
reasoning pass, not a fact to preserve historically), and the repository
also exposes the same bare `commit()` passthrough every aggregate-root
repository in this codebase provides, used by `AIAgentsService` to
durably persist Research Dossier evidence rows on the same shared
session (see `ai_agents/service.py`).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.ai_agents.models import AgentFinding


class AgentFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest(self, company_id: uuid.UUID, agent_code: str) -> AgentFinding | None:
        result = await self._session.execute(
            select(AgentFinding).where(
                AgentFinding.company_id == company_id,
                AgentFinding.agent_code == agent_code,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        company_id: uuid.UUID,
        agent_code: str,
        result_json: dict,
        prompt_version: str,
        model_used: str,
        confidence_score: float,
        evidence_sufficiency: str,
    ) -> None:
        statement = pg_insert(AgentFinding).values(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_code=agent_code,
            result_json=result_json,
            prompt_version=prompt_version,
            model_used=model_used,
            confidence_score=confidence_score,
            evidence_sufficiency=evidence_sufficiency,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["company_id", "agent_code"],
            set_={
                "result_json": statement.excluded.result_json,
                "prompt_version": statement.excluded.prompt_version,
                "model_used": statement.excluded.model_used,
                "confidence_score": statement.excluded.confidence_score,
                "evidence_sufficiency": statement.excluded.evidence_sufficiency,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()

    async def commit(self) -> None:
        await self._session.commit()
