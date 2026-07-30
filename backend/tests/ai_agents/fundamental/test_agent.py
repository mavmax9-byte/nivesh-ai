import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from nivesh.ai_agents.agents.base import AgentContext
from nivesh.ai_agents.agents.fundamental.agent import FundamentalAnalystAgent
from nivesh.ai_agents.agents.fundamental.validation import InvestmentAdviceDetectedError
from nivesh.ai_agents.providers.base import LLMCompletion
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError
from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.retrieval_engine.normalization import ContextPackage, EvidenceItem


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid.uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid.uuid4(),
        symbol=symbol,
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )
    company.exchange = exchange
    return company


def _evidence_item(source_type: str = "financial_statement", **overrides) -> EvidenceItem:
    defaults = dict(
        source_type=source_type,
        source_table="financial_statements",
        source_id=uuid.uuid4(),
        title="Q1 FY26 statement",
        snippet="Revenue: 1000, Net income: 200.",
        evidence_date=date(2026, 6, 30),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _context_package(symbol: str, evidence: list[EvidenceItem]) -> ContextPackage:
    return ContextPackage(
        symbol=symbol,
        query="revenue growth, profitability, margins",
        generated_at=datetime.now(UTC),
        evidence=tuple(evidence),
        context_text="Evidence for " + symbol,
    )


def _llm_completion(parsed_json: dict) -> LLMCompletion:
    return LLMCompletion(
        raw_text="{}",
        parsed_json=parsed_json,
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        finish_reason="stop",
    )


def _valid_llm_output(citation_refs: list[int] | None = None) -> dict:
    return {
        "summary": "The company shows steady revenue growth backed by the evidence.",
        "strengths": [
            {
                "metric": "revenue_growth",
                "observation": "Revenue increased versus the prior period.",
                "citation_refs": citation_refs if citation_refs is not None else [1],
            }
        ],
        "concerns": [],
        "financial_health_assessment": "The balance sheet appears stable based on the evidence.",
        "evidence_sufficiency": "sufficient",
        "llm_confidence": 0.8,
    }


def _make_agent(company, evidence, llm_parsed_json=None, llm_side_effect=None):
    company_repository = AsyncMock()
    company_repository.get_by_id.return_value = company

    retrieval_service = AsyncMock()
    retrieval_service.build_context_package.return_value = _context_package(
        company.symbol, evidence
    )

    llm_provider = AsyncMock()
    if llm_side_effect is not None:
        llm_provider.complete.side_effect = llm_side_effect
    else:
        llm_provider.complete.return_value = _llm_completion(
            llm_parsed_json if llm_parsed_json is not None else _valid_llm_output()
        )

    agent = FundamentalAnalystAgent(
        retrieval_service=retrieval_service,
        llm_provider=llm_provider,
        company_repository=company_repository,
    )
    return agent, retrieval_service, llm_provider


@pytest.mark.asyncio
async def test_run_raises_not_found_for_unknown_company_id():
    company_repository = AsyncMock()
    company_repository.get_by_id.return_value = None
    agent = FundamentalAnalystAgent(
        retrieval_service=AsyncMock(),
        llm_provider=AsyncMock(),
        company_repository=company_repository,
    )
    with pytest.raises(NotFoundError):
        await agent.run(AgentContext(company_id=str(uuid.uuid4()), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_returns_insufficient_evidence_without_calling_llm():
    company = _company()
    evidence = [_evidence_item(source_type="news_article")]  # no financial_statement
    agent, retrieval_service, llm_provider = _make_agent(company, evidence)

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.detail["evidence_sufficiency"] == "insufficient"
    assert finding.evidence_ids == []
    llm_provider.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_produces_cited_finding_when_evidence_sufficient():
    company = _company()
    evidence = [_evidence_item()]
    agent, retrieval_service, llm_provider = _make_agent(company, evidence)

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.agent_code == "fundamental_analyst"
    assert finding.detail["evidence_sufficiency"] == "sufficient"
    assert len(finding.detail["citations"]) == 1
    assert finding.detail["citations"][0]["source_id"] == str(evidence[0].source_id)
    assert finding.evidence_ids == [str(evidence[0].source_id)]
    llm_provider.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_drops_claims_citing_out_of_range_evidence():
    company = _company()
    evidence = [_evidence_item()]
    agent, retrieval_service, llm_provider = _make_agent(
        company, evidence, llm_parsed_json=_valid_llm_output(citation_refs=[99])
    )

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.detail["strengths"] == []
    assert any("removed" in caveat for caveat in finding.detail["caveats"])


@pytest.mark.asyncio
async def test_run_raises_on_investment_advice_language():
    company = _company()
    evidence = [_evidence_item()]
    bad_output = _valid_llm_output()
    bad_output["summary"] = "Investors should buy this stock immediately."
    agent, retrieval_service, llm_provider = _make_agent(
        company, evidence, llm_parsed_json=bad_output
    )

    with pytest.raises(InvestmentAdviceDetectedError):
        await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_raises_parsing_error_on_schema_mismatch():
    company = _company()
    evidence = [_evidence_item()]
    agent, retrieval_service, llm_provider = _make_agent(
        company, evidence, llm_parsed_json={"unexpected": "shape"}
    )

    with pytest.raises(LLMResponseParsingError):
        await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_confidence_score_never_exceeds_evidence_confidence():
    company = _company()
    evidence = [_evidence_item()]  # financial_statement only -> bounded evidence_confidence
    high_confidence_output = _valid_llm_output()
    high_confidence_output["llm_confidence"] = 1.0
    agent, retrieval_service, llm_provider = _make_agent(
        company, evidence, llm_parsed_json=high_confidence_output
    )

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.confidence_score < 1.0
