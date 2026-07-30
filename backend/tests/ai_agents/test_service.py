import uuid
from unittest.mock import AsyncMock

import pytest

from nivesh.ai_agents.agents.base import AgentFinding
from nivesh.ai_agents.models import AgentFinding as AgentFindingRow
from nivesh.ai_agents.service import AIAgentsService
from nivesh.core.exceptions import NotFoundError


def _company(company_id: uuid.UUID, symbol: str = "TCS"):
    company = AsyncMock()
    company.id = company_id
    company.symbol = symbol
    return company


def _finding() -> AgentFinding:
    return AgentFinding(
        agent_code="fundamental_analyst",
        summary="Revenue grew steadily.",
        confidence_score=0.6,
        evidence_ids=[str(uuid.uuid4())],
        detail={
            "prompt_version": "fundamental-v1",
            "model_used": "gpt-4o-mini",
            "evidence_sufficiency": "sufficient",
        },
    )


def _make_service(company, finding, *, has_research_version: bool, persisted_finding=None):
    agent = AsyncMock()
    agent.agent_code = "fundamental_analyst"
    agent.run.return_value = finding

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    finding_repository = AsyncMock()
    finding_repository.get_latest.return_value = persisted_finding

    dossier_repository = AsyncMock()
    dossier = AsyncMock()
    dossier.id = uuid.uuid4()
    dossier_repository.get_or_create_dossier.return_value = dossier
    if has_research_version:
        version = AsyncMock()
        version.id = uuid.uuid4()
        dossier_repository.get_latest_version.return_value = version
    else:
        dossier_repository.get_latest_version.return_value = None

    service = AIAgentsService(
        agent=agent,
        company_repository=company_repository,
        finding_repository=finding_repository,
        dossier_repository=dossier_repository,
    )
    return service, agent, company_repository, finding_repository, dossier_repository


@pytest.mark.asyncio
async def test_run_analysis_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = AIAgentsService(
        agent=AsyncMock(),
        company_repository=company_repository,
        finding_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await service.run_analysis("NOPE")


@pytest.mark.asyncio
async def test_run_analysis_persists_finding_and_links_dossier():
    company_id = uuid.uuid4()
    company = _company(company_id)
    finding = _finding()
    persisted_row = AgentFindingRow(
        id=uuid.uuid4(), company_id=company_id, agent_code="fundamental_analyst"
    )
    service, agent, company_repository, finding_repository, dossier_repository = _make_service(
        company, finding, has_research_version=True, persisted_finding=persisted_row
    )

    result = await service.run_analysis("TCS")

    assert result.company_id == company_id
    assert result.symbol == "TCS"
    assert result.agent_code == "fundamental_analyst"
    finding_repository.upsert.assert_awaited_once()
    upsert_kwargs = finding_repository.upsert.await_args.kwargs
    assert upsert_kwargs["company_id"] == company_id
    assert upsert_kwargs["agent_code"] == "fundamental_analyst"
    assert upsert_kwargs["confidence_score"] == finding.confidence_score

    dossier_repository.bulk_create_sources.assert_awaited_once()
    source_rows = dossier_repository.bulk_create_sources.await_args.args[0]
    assert source_rows[0]["source_type"] == "agent_finding"
    assert source_rows[0]["reference_id"] == persisted_row.id
    assert source_rows[0]["record_count"] == 1
    dossier_repository.create_timeline_event.assert_awaited_once()
    finding_repository.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_analysis_skips_dossier_link_when_no_research_version_exists():
    company_id = uuid.uuid4()
    company = _company(company_id)
    finding = _finding()
    service, agent, company_repository, finding_repository, dossier_repository = _make_service(
        company, finding, has_research_version=False
    )

    await service.run_analysis("TCS")

    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_latest_finding_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = AIAgentsService(
        agent=AsyncMock(),
        company_repository=company_repository,
        finding_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await service.get_latest_finding("NOPE")


@pytest.mark.asyncio
async def test_persist_finding_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = AIAgentsService(
        agent=None,
        company_repository=company_repository,
        finding_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await service.persist_finding("NOPE", _finding())


@pytest.mark.asyncio
async def test_persist_finding_persists_and_links_without_a_concrete_agent():
    """v1.0: the Investment Committee orchestrator constructs this service
    with agent=None (persist-only mode) for the Chair's and Compliance's
    own findings, which aren't produced by a BaseAgent.run() call."""
    company_id = uuid.uuid4()
    company = _company(company_id)
    finding = AgentFinding(
        agent_code="investment_committee",
        summary="Overall the fundamentals look steady.",
        confidence_score=0.65,
        evidence_ids=[],
        detail={"prompt_version": "committee-chair-v1", "model_used": "gpt-4o-mini"},
    )
    persisted_row = AgentFindingRow(
        id=uuid.uuid4(), company_id=company_id, agent_code="investment_committee"
    )
    service, agent, company_repository, finding_repository, dossier_repository = _make_service(
        company, finding, has_research_version=True, persisted_finding=persisted_row
    )
    service = AIAgentsService(
        agent=None,
        company_repository=company_repository,
        finding_repository=finding_repository,
        dossier_repository=dossier_repository,
    )

    result = await service.persist_finding("TCS", finding)

    assert result.agent_code == "investment_committee"
    finding_repository.upsert.assert_awaited_once()
    upsert_kwargs = finding_repository.upsert.await_args.kwargs
    assert upsert_kwargs["agent_code"] == "investment_committee"
    dossier_repository.bulk_create_sources.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_finding_skips_dossier_link_when_requested():
    """Compliance's own verdict is an audit record of the review, not a
    new piece of evidence about the company -- the orchestrator passes
    link_to_dossier=False for it (INVESTMENT_COMMITTEE_DESIGN.md §10)."""
    company_id = uuid.uuid4()
    company = _company(company_id)
    finding = AgentFinding(
        agent_code="compliance_review",
        summary="Committee decision approved for publication.",
        confidence_score=1.0,
        evidence_ids=[],
        detail={"approved": True, "reasons": []},
    )
    service, agent, company_repository, finding_repository, dossier_repository = _make_service(
        company, finding, has_research_version=True
    )
    service = AIAgentsService(
        agent=None,
        company_repository=company_repository,
        finding_repository=finding_repository,
        dossier_repository=dossier_repository,
    )

    await service.persist_finding("TCS", finding, link_to_dossier=False)

    finding_repository.upsert.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_analysis_raises_when_constructed_without_agent():
    service = AIAgentsService(
        agent=None,
        company_repository=AsyncMock(),
        finding_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )
    with pytest.raises(NotImplementedError):
        await service.run_analysis("TCS")


@pytest.mark.asyncio
async def test_get_latest_finding_returns_repository_result():
    company_id = uuid.uuid4()
    company = _company(company_id)
    agent = AsyncMock()
    agent.agent_code = "fundamental_analyst"

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    finding_repository = AsyncMock()
    expected = AgentFindingRow(id=uuid.uuid4(), company_id=company_id, agent_code=agent.agent_code)
    finding_repository.get_latest.return_value = expected

    service = AIAgentsService(
        agent=agent,
        company_repository=company_repository,
        finding_repository=finding_repository,
        dossier_repository=AsyncMock(),
    )

    result = await service.get_latest_finding("TCS")

    assert result is expected
    finding_repository.get_latest.assert_awaited_once_with(company_id, "fundamental_analyst")
