"""Repository tests against a real PostgreSQL test database.

Mirrors technical_intelligence's own test_repositories.py precedent:
AgentFindingRepository is an upsert-only, single-table repository (see
models.py's module docstring) -- these tests exercise the real
`ON CONFLICT DO UPDATE` behavior on `(company_id, agent_code)`, which
cannot be meaningfully faked with an in-memory database.
"""

import uuid

import pytest

from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.companies.repository import CompanyRepository, ExchangeRepository


async def _make_company(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")
    return await company_repository.upsert(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_no_finding_exists(db_session):
    company = await _make_company(db_session)
    repository = AgentFindingRepository(db_session)

    finding = await repository.get_latest(company.id, "fundamental_analyst")

    assert finding is None


@pytest.mark.asyncio
async def test_upsert_creates_a_new_finding(db_session):
    company = await _make_company(db_session)
    repository = AgentFindingRepository(db_session)

    await repository.upsert(
        company_id=company.id,
        agent_code="fundamental_analyst",
        result_json={"summary": "first run"},
        prompt_version="fundamental-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.4,
        evidence_sufficiency="partial",
    )

    finding = await repository.get_latest(company.id, "fundamental_analyst")
    assert finding is not None
    assert finding.result_json == {"summary": "first run"}
    assert finding.confidence_score == pytest.approx(0.4)
    assert finding.evidence_sufficiency == "partial"


@pytest.mark.asyncio
async def test_upsert_overwrites_existing_finding_for_same_company_and_agent(db_session):
    company = await _make_company(db_session)
    repository = AgentFindingRepository(db_session)

    await repository.upsert(
        company_id=company.id,
        agent_code="fundamental_analyst",
        result_json={"summary": "first run"},
        prompt_version="fundamental-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.4,
        evidence_sufficiency="partial",
    )
    await repository.upsert(
        company_id=company.id,
        agent_code="fundamental_analyst",
        result_json={"summary": "second run"},
        prompt_version="fundamental-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
    )

    findings = await repository.get_latest(company.id, "fundamental_analyst")
    assert findings is not None
    assert findings.result_json == {"summary": "second run"}
    assert findings.confidence_score == pytest.approx(0.7)
    assert findings.evidence_sufficiency == "sufficient"


@pytest.mark.asyncio
async def test_findings_are_scoped_per_agent_code(db_session):
    company = await _make_company(db_session)
    repository = AgentFindingRepository(db_session)

    await repository.upsert(
        company_id=company.id,
        agent_code="fundamental_analyst",
        result_json={"summary": "fundamental"},
        prompt_version="fundamental-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.5,
        evidence_sufficiency="sufficient",
    )
    await repository.upsert(
        company_id=company.id,
        agent_code="another_agent",
        result_json={"summary": "another"},
        prompt_version="another-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.9,
        evidence_sufficiency="sufficient",
    )

    fundamental = await repository.get_latest(company.id, "fundamental_analyst")
    other = await repository.get_latest(company.id, "another_agent")

    assert fundamental is not None and fundamental.result_json == {"summary": "fundamental"}
    assert other is not None and other.result_json == {"summary": "another"}


@pytest.mark.asyncio
async def test_get_latest_returns_none_for_unknown_company(db_session):
    repository = AgentFindingRepository(db_session)
    finding = await repository.get_latest(uuid.uuid4(), "fundamental_analyst")
    assert finding is None
