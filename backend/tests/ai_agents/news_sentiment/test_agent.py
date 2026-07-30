import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from nivesh.ai_agents.agents.base import AgentContext
from nivesh.ai_agents.agents.news_sentiment.agent import NewsSentimentAnalystAgent
from nivesh.ai_agents.guardrails import InvestmentAdviceDetectedError
from nivesh.ai_agents.providers.base import LLMCompletion
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError
from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.retrieval_engine.normalization import ContextPackage, EvidenceItem


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid.uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid.uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _evidence_item(source_type: str = "news_article", **overrides) -> EvidenceItem:
    defaults = dict(
        source_type=source_type,
        source_table="news_articles",
        source_id=uuid.uuid4(),
        title="Contract win reported",
        snippet="The company reported a new contract.",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _context_package(symbol: str, evidence: list[EvidenceItem]) -> ContextPackage:
    return ContextPackage(
        symbol=symbol,
        query="recent news sentiment",
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
        "summary": "Recent coverage is broadly positive.",
        "findings": [
            {
                "metric": "contract_win",
                "observation": "A new contract win was reported.",
                "stance": "positive",
                "citation_refs": citation_refs if citation_refs is not None else [1],
            }
        ],
        "sentiment_assessment": "Sentiment is positive based on recent coverage.",
        "evidence_sufficiency": "sufficient",
        "llm_confidence": 0.8,
    }


def _make_agent(company, evidence, llm_parsed_json=None, shared_evidence=None):
    company_repository = AsyncMock()
    company_repository.get_by_id.return_value = company

    retrieval_service = AsyncMock()
    retrieval_service.build_context_package.return_value = _context_package(
        company.symbol, evidence
    )

    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(
        llm_parsed_json if llm_parsed_json is not None else _valid_llm_output()
    )

    agent = NewsSentimentAnalystAgent(
        retrieval_service=retrieval_service,
        llm_provider=llm_provider,
        company_repository=company_repository,
        shared_evidence=shared_evidence,
    )
    return agent, retrieval_service, llm_provider


@pytest.mark.asyncio
async def test_run_raises_not_found_for_unknown_company_id():
    company_repository = AsyncMock()
    company_repository.get_by_id.return_value = None
    agent = NewsSentimentAnalystAgent(
        retrieval_service=AsyncMock(),
        llm_provider=AsyncMock(),
        company_repository=company_repository,
    )
    with pytest.raises(NotFoundError):
        await agent.run(AgentContext(company_id=str(uuid.uuid4()), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_returns_insufficient_evidence_without_calling_llm():
    company = _company()
    evidence = [_evidence_item(source_type="financial_statement")]
    agent, retrieval_service, llm_provider = _make_agent(company, evidence)

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.detail["evidence_sufficiency"] == "insufficient"
    llm_provider.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_produces_cited_finding_when_evidence_sufficient():
    company = _company()
    evidence = [_evidence_item()]
    agent, retrieval_service, llm_provider = _make_agent(company, evidence)

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.agent_code == "news_sentiment_analyst"
    assert len(finding.detail["citations"]) == 1
    llm_provider.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_raises_on_investment_advice_language():
    company = _company()
    evidence = [_evidence_item()]
    bad_output = _valid_llm_output()
    bad_output["summary"] = "Investors should accumulate this stock."
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
async def test_run_uses_shared_evidence_pool_without_calling_retrieval_engine():
    company = _company()
    shared_pool = [_evidence_item()]
    agent, retrieval_service, llm_provider = _make_agent(
        company, evidence=[], shared_evidence=shared_pool
    )

    await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    retrieval_service.build_context_package.assert_not_awaited()
