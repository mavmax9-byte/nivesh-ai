import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from nivesh.ai_agents.agents.base import AgentContext
from nivesh.ai_agents.agents.valuation.agent import ValuationAnalystAgent
from nivesh.ai_agents.guardrails import InvestmentAdviceDetectedError
from nivesh.ai_agents.providers.base import LLMCompletion
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError
from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.financials.models import FinancialStatement, ProfitAndLoss
from nivesh.retrieval_engine.normalization import ContextPackage, EvidenceItem


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid.uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid.uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _statement(statement_id: uuid.UUID, eps_basic=Decimal("10")) -> FinancialStatement:
    statement = FinancialStatement(
        id=statement_id,
        company_id=uuid.uuid4(),
        period_type="quarterly",
        fiscal_year=2026,
        fiscal_period="Q1",
        period_end_date=date(2026, 6, 30),
        currency="INR",
        version=1,
        source="test",
    )
    statement.profit_and_loss = ProfitAndLoss(
        id=uuid.uuid4(),
        financial_statement_id=statement_id,
        total_revenue=Decimal("1000"),
        net_income=Decimal("200"),
        eps_basic=eps_basic,
    )
    return statement


def _evidence_item(source_type: str = "financial_statement", **overrides) -> EvidenceItem:
    defaults = dict(
        source_type=source_type,
        source_table="financial_statements",
        source_id=uuid.uuid4(),
        title="Q1 FY26 statement",
        snippet="EPS: 10.00",
        evidence_date=date(2026, 6, 30),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _context_package(symbol: str, evidence: list[EvidenceItem]) -> ContextPackage:
    return ContextPackage(
        symbol=symbol,
        query="valuation",
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
        "summary": "Valuation appears reasonable given reported earnings.",
        "findings": [
            {
                "metric": "pe_ratio",
                "observation": "The computed P/E ratio is within a typical range.",
                "stance": "neutral",
                "citation_refs": citation_refs if citation_refs is not None else [1],
            }
        ],
        "valuation_assessment": "The valuation is broadly in line with earnings.",
        "evidence_sufficiency": "sufficient",
        "llm_confidence": 0.8,
    }


def _no_dossier_version(dossier_repository):
    dossier_repository.get_by_company_id.return_value = None


def _with_dossier_version(dossier_repository, price=Decimal("500"), trade_date=date(2026, 7, 1)):
    dossier = AsyncMock()
    dossier.id = uuid.uuid4()
    dossier_repository.get_by_company_id.return_value = dossier
    version = AsyncMock()
    version.snapshot = AsyncMock()
    version.snapshot.latest_price = price
    version.snapshot.latest_trade_date = trade_date
    dossier_repository.get_latest_version.return_value = version


def _make_agent(
    company,
    evidence,
    llm_parsed_json=None,
    shared_evidence=None,
    statement=None,
    dossier_has_price=True,
):
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

    statement_repository = AsyncMock()
    statement_repository.get_by_id.return_value = statement

    dossier_repository = AsyncMock()
    if dossier_has_price:
        _with_dossier_version(dossier_repository)
    else:
        _no_dossier_version(dossier_repository)

    agent = ValuationAnalystAgent(
        retrieval_service=retrieval_service,
        llm_provider=llm_provider,
        company_repository=company_repository,
        statement_repository=statement_repository,
        dossier_repository=dossier_repository,
        shared_evidence=shared_evidence,
    )
    return agent, retrieval_service, llm_provider, statement_repository, dossier_repository


@pytest.mark.asyncio
async def test_run_raises_not_found_for_unknown_company_id():
    company_repository = AsyncMock()
    company_repository.get_by_id.return_value = None
    agent = ValuationAnalystAgent(
        retrieval_service=AsyncMock(),
        llm_provider=AsyncMock(),
        company_repository=company_repository,
        statement_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await agent.run(AgentContext(company_id=str(uuid.uuid4()), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_returns_insufficient_evidence_without_calling_llm():
    company = _company()
    evidence = [_evidence_item(source_type="news_article")]
    agent, retrieval_service, llm_provider, _, _ = _make_agent(company, evidence)

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert finding.detail["evidence_sufficiency"] == "insufficient"
    llm_provider.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_appends_computed_pe_ratio_as_synthetic_evidence():
    company = _company()
    statement_id = uuid.uuid4()
    evidence = [_evidence_item(source_id=statement_id)]
    statement = _statement(statement_id)
    agent, retrieval_service, llm_provider, statement_repository, dossier_repository = _make_agent(
        company, evidence, statement=statement, dossier_has_price=True
    )

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    statement_repository.get_by_id.assert_awaited_once_with(statement_id)
    # The LLM should have been shown 2 evidence items (retrieved + computed ratio).
    user_prompt = llm_provider.complete.await_args.args[1]
    assert "[2]" in user_prompt
    assert "Computed price-to-earnings" in user_prompt
    assert any("does not ingest shares-outstanding" in c for c in finding.detail["caveats"])


@pytest.mark.asyncio
async def test_run_adds_caveat_when_no_price_snapshot_available():
    company = _company()
    statement_id = uuid.uuid4()
    evidence = [_evidence_item(source_id=statement_id)]
    statement = _statement(statement_id)
    agent, retrieval_service, llm_provider, statement_repository, dossier_repository = _make_agent(
        company, evidence, statement=statement, dossier_has_price=False
    )

    finding = await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    assert any("no market price snapshot" in c for c in finding.detail["caveats"])


@pytest.mark.asyncio
async def test_run_raises_on_investment_advice_language():
    company = _company()
    statement_id = uuid.uuid4()
    evidence = [_evidence_item(source_id=statement_id)]
    statement = _statement(statement_id)
    bad_output = _valid_llm_output()
    bad_output["summary"] = "This valuation means investors should buy now."
    agent, retrieval_service, llm_provider, _, _ = _make_agent(
        company, evidence, llm_parsed_json=bad_output, statement=statement
    )

    with pytest.raises(InvestmentAdviceDetectedError):
        await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_raises_parsing_error_on_schema_mismatch():
    company = _company()
    statement_id = uuid.uuid4()
    evidence = [_evidence_item(source_id=statement_id)]
    statement = _statement(statement_id)
    agent, retrieval_service, llm_provider, _, _ = _make_agent(
        company, evidence, llm_parsed_json={"unexpected": "shape"}, statement=statement
    )

    with pytest.raises(LLMResponseParsingError):
        await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))


@pytest.mark.asyncio
async def test_run_uses_shared_evidence_pool_without_calling_retrieval_engine():
    company = _company()
    statement_id = uuid.uuid4()
    shared_pool = [_evidence_item(source_id=statement_id)]
    statement = _statement(statement_id)
    agent, retrieval_service, llm_provider, _, _ = _make_agent(
        company, evidence=[], shared_evidence=shared_pool, statement=statement
    )

    await agent.run(AgentContext(company_id=str(company.id), trigger_type="manual"))

    retrieval_service.build_context_package.assert_not_awaited()
