import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nivesh.ai_agents.committee.exceptions import (
    CommitteeQuorumNotMetError,
    ComplianceRejectedError,
)
from nivesh.ai_agents.models import SPECIALIST_AGENT_CODES
from nivesh.ai_agents.orchestrator import InvestmentCommitteeOrchestrator
from nivesh.ai_agents.providers.base import LLMCompletion
from nivesh.core.exceptions import NotFoundError
from nivesh.retrieval_engine.normalization import ContextPackage


def _company(symbol: str = "TCS") -> MagicMock:
    company = MagicMock()
    company.id = uuid.uuid4()
    company.symbol = symbol
    return company


def _finding_row(agent_code: str, result_json: dict | None = None) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.confidence_score = 0.7
    row.evidence_sufficiency = "sufficient"
    row.result_json = (
        result_json if result_json is not None else {"summary": f"{agent_code} says ok"}
    )
    return row


def _llm_completion(parsed_json: dict) -> LLMCompletion:
    return LLMCompletion(
        raw_text="{}",
        parsed_json=parsed_json,
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=80,
        finish_reason="stop",
    )


def _valid_chair_output(citation_refs: list[int] | None = None) -> dict:
    return {
        "summary": "Overall the fundamentals look steady.",
        "findings": [
            {
                "theme": "growth",
                "observation": "Revenue growth is a consistent theme.",
                "stance": "positive",
                "citation_refs": citation_refs if citation_refs is not None else [1],
            }
        ],
        "disagreements": [],
        "llm_confidence": 0.8,
    }


def _fundamental_result_json() -> dict:
    source_id = uuid.uuid4()
    return {
        "summary": "Revenue grew steadily.",
        "financial_health_assessment": "Balance sheet is stable.",
        "strengths": [{"metric": "revenue", "observation": "Revenue grew", "citation_refs": [1]}],
        "concerns": [],
        "citations": [
            {
                "index": 1,
                "source_type": "financial_statement",
                "source_table": "financial_statements",
                "source_id": str(source_id),
                "title": "Q1 FY26 statement",
                "evidence_date": "2026-06-30",
            }
        ],
    }


def _make_service_factory(failing_agent_codes: set[str], persisted: list):
    def factory(
        agent=None, company_repository=None, finding_repository=None, dossier_repository=None
    ):
        agent_code = agent.agent_code if agent is not None else None

        class _Service:
            async def run_analysis(self, symbol: str):
                if agent_code in failing_agent_codes:
                    raise RuntimeError(f"{agent_code} failed")
                return MagicMock()

            async def persist_finding(self, symbol: str, finding, *, link_to_dossier: bool = True):
                persisted.append((finding.agent_code, finding))

        return _Service()

    return factory


def _context_package() -> ContextPackage:
    return ContextPackage(
        symbol="TCS",
        query="committee",
        generated_at=datetime.now(UTC),
        evidence=(),
        context_text="",
    )


def _build_orchestrator(company, failing_agent_codes, chair_output, findings_by_code, persisted):
    retrieval_service = AsyncMock()
    retrieval_service.build_context_package.return_value = _context_package()

    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(chair_output)

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    finding_repository = AsyncMock()
    finding_repository.get_latest.side_effect = lambda company_id, agent_code: findings_by_code.get(
        agent_code
    )

    orchestrator = InvestmentCommitteeOrchestrator(
        retrieval_service=retrieval_service,
        llm_provider=llm_provider,
        company_repository=company_repository,
        statement_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
        finding_repository=finding_repository,
    )

    factory = _make_service_factory(failing_agent_codes, persisted)
    return orchestrator, retrieval_service, llm_provider, factory


@pytest.mark.asyncio
async def test_run_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    orchestrator = InvestmentCommitteeOrchestrator(
        retrieval_service=AsyncMock(),
        llm_provider=AsyncMock(),
        company_repository=company_repository,
        statement_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
        finding_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await orchestrator.run("NOPE")


@pytest.mark.asyncio
async def test_run_succeeds_with_all_five_specialists():
    company = _company()
    findings_by_code = {
        "fundamental_analyst": _finding_row("fundamental_analyst", _fundamental_result_json()),
        **{
            code: _finding_row(code)
            for code in SPECIALIST_AGENT_CODES
            if code != "fundamental_analyst"
        },
    }
    persisted: list = []
    orchestrator, retrieval_service, llm_provider, factory = _build_orchestrator(
        company,
        failing_agent_codes=set(),
        chair_output=_valid_chair_output(),
        findings_by_code=findings_by_code,
        persisted=persisted,
    )

    with patch("nivesh.ai_agents.orchestrator.AIAgentsService", side_effect=factory):
        result = await orchestrator.run("TCS")

    retrieval_service.build_context_package.assert_awaited_once()
    assert set(result.succeeded_specialists) == set(SPECIALIST_AGENT_CODES)
    assert result.failed_specialists == []
    assert result.compliance_approved is True
    persisted_codes = [agent_code for agent_code, _ in persisted]
    assert "investment_committee" in persisted_codes
    assert "compliance_review" in persisted_codes


@pytest.mark.asyncio
async def test_run_degrades_gracefully_when_optional_specialist_fails():
    company = _company()
    findings_by_code = {
        "fundamental_analyst": _finding_row("fundamental_analyst", _fundamental_result_json()),
        "valuation_analyst": _finding_row("valuation_analyst"),
        "news_sentiment_analyst": _finding_row("news_sentiment_analyst"),
        "risk_analyst": _finding_row("risk_analyst"),
    }
    persisted: list = []
    orchestrator, retrieval_service, llm_provider, factory = _build_orchestrator(
        company,
        failing_agent_codes={"technical_analyst"},
        chair_output=_valid_chair_output(),
        findings_by_code=findings_by_code,
        persisted=persisted,
    )

    with patch("nivesh.ai_agents.orchestrator.AIAgentsService", side_effect=factory):
        result = await orchestrator.run("TCS")

    assert "technical_analyst" not in result.succeeded_specialists
    assert result.failed_specialists == ["technical_analyst"]
    assert result.compliance_approved is True


@pytest.mark.asyncio
async def test_run_raises_quorum_error_when_fundamental_fails():
    company = _company()
    findings_by_code = {
        code: _finding_row(code) for code in SPECIALIST_AGENT_CODES if code != "fundamental_analyst"
    }
    persisted: list = []
    orchestrator, retrieval_service, llm_provider, factory = _build_orchestrator(
        company,
        failing_agent_codes={"fundamental_analyst"},
        chair_output=_valid_chair_output(),
        findings_by_code=findings_by_code,
        persisted=persisted,
    )

    with (
        patch("nivesh.ai_agents.orchestrator.AIAgentsService", side_effect=factory),
        pytest.raises(CommitteeQuorumNotMetError),
    ):
        await orchestrator.run("TCS")

    llm_provider.complete.assert_not_awaited()
    assert persisted == []


@pytest.mark.asyncio
async def test_run_raises_quorum_error_when_all_specialists_fail():
    company = _company()
    persisted: list = []
    orchestrator, retrieval_service, llm_provider, factory = _build_orchestrator(
        company,
        failing_agent_codes=set(SPECIALIST_AGENT_CODES),
        chair_output=_valid_chair_output(),
        findings_by_code={},
        persisted=persisted,
    )

    with (
        patch("nivesh.ai_agents.orchestrator.AIAgentsService", side_effect=factory),
        pytest.raises(CommitteeQuorumNotMetError),
    ):
        await orchestrator.run("TCS")


@pytest.mark.asyncio
async def test_run_raises_compliance_rejected_but_persists_audit_rows_first():
    company = _company()
    findings_by_code = {
        "fundamental_analyst": _finding_row("fundamental_analyst", _fundamental_result_json()),
        "valuation_analyst": _finding_row("valuation_analyst"),
        "news_sentiment_analyst": _finding_row("news_sentiment_analyst"),
        "risk_analyst": _finding_row("risk_analyst"),
    }
    persisted: list = []
    advice_output = _valid_chair_output()
    advice_output["summary"] = "Investors should buy this stock now."
    orchestrator, retrieval_service, llm_provider, factory = _build_orchestrator(
        company,
        failing_agent_codes={"technical_analyst"},
        chair_output=advice_output,
        findings_by_code=findings_by_code,
        persisted=persisted,
    )

    with (
        patch("nivesh.ai_agents.orchestrator.AIAgentsService", side_effect=factory),
        pytest.raises(ComplianceRejectedError),
    ):
        await orchestrator.run("TCS")

    persisted_codes = [agent_code for agent_code, _ in persisted]
    assert "investment_committee" in persisted_codes
    assert "compliance_review" in persisted_codes
    compliance_finding = next(f for code, f in persisted if code == "compliance_review")
    assert compliance_finding.detail["approved"] is False
