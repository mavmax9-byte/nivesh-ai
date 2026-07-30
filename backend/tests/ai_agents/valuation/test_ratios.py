import uuid
from datetime import date
from decimal import Decimal

from nivesh.ai_agents.agents.valuation.ratios import (
    EVIDENCE_SOURCE_COMPUTED_RATIO,
    PB_UNAVAILABLE_CAVEAT,
    compute_price_to_earnings,
)
from nivesh.financials.models import FinancialStatement, ProfitAndLoss


def _statement(eps_basic=None, eps_diluted=None) -> FinancialStatement:
    statement = FinancialStatement(
        id=uuid.uuid4(),
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
        financial_statement_id=statement.id,
        total_revenue=Decimal("1000"),
        net_income=Decimal("200"),
        eps_basic=eps_basic,
        eps_diluted=eps_diluted,
    )
    return statement


def test_pb_unavailable_caveat_is_always_present_regardless_of_pe_outcome():
    result_with_pe = compute_price_to_earnings(
        statement=_statement(eps_basic=Decimal("10")),
        latest_price=Decimal("500"),
        latest_trade_date=date(2026, 7, 1),
    )
    result_without_pe = compute_price_to_earnings(
        statement=None, latest_price=None, latest_trade_date=None
    )
    assert PB_UNAVAILABLE_CAVEAT in result_with_pe.caveats
    assert PB_UNAVAILABLE_CAVEAT in result_without_pe.caveats


def test_compute_price_to_earnings_returns_none_when_price_missing():
    result = compute_price_to_earnings(
        statement=_statement(eps_basic=Decimal("10")), latest_price=None, latest_trade_date=None
    )
    assert result.evidence_item is None
    assert any("no market price snapshot" in c for c in result.caveats)


def test_compute_price_to_earnings_returns_none_when_statement_missing():
    result = compute_price_to_earnings(
        statement=None, latest_price=Decimal("500"), latest_trade_date=date(2026, 7, 1)
    )
    assert result.evidence_item is None
    assert any("no financial statement" in c for c in result.caveats)


def test_compute_price_to_earnings_returns_none_when_eps_non_positive():
    result = compute_price_to_earnings(
        statement=_statement(eps_basic=Decimal("0")),
        latest_price=Decimal("500"),
        latest_trade_date=date(2026, 7, 1),
    )
    assert result.evidence_item is None
    assert any("non-positive" in c for c in result.caveats)


def test_compute_price_to_earnings_computes_ratio_from_eps_basic():
    statement = _statement(eps_basic=Decimal("10"))
    result = compute_price_to_earnings(
        statement=statement, latest_price=Decimal("500"), latest_trade_date=date(2026, 7, 1)
    )
    assert result.evidence_item is not None
    assert result.evidence_item.source_type == EVIDENCE_SOURCE_COMPUTED_RATIO
    assert result.evidence_item.source_id == statement.id
    assert "50.00" in result.evidence_item.snippet


def test_compute_price_to_earnings_falls_back_to_eps_diluted():
    statement = _statement(eps_basic=None, eps_diluted=Decimal("20"))
    result = compute_price_to_earnings(
        statement=statement, latest_price=Decimal("400"), latest_trade_date=date(2026, 7, 1)
    )
    assert result.evidence_item is not None
    assert "20.00" in result.evidence_item.snippet
