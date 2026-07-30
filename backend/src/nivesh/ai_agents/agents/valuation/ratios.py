"""Deterministic valuation-ratio computation for the Valuation Analyst.

Computes P/E from a company's latest available EPS (financials module) and
latest known price (Research Dossier snapshot) -- pure arithmetic, never an
LLM call, per INVESTMENT_COMMITTEE_DESIGN.md §3a. The result is packaged as
a synthetic "computed_ratio" evidence item so it flows through the exact
same citation/prompt machinery as retrieved evidence, with its own citation
pointing back at the underlying `FinancialStatement` row.
`EVIDENCE_SOURCE_COMPUTED_RATIO` is scoped to this one agent, not added to
`retrieval_engine`'s own `EVIDENCE_SOURCE_*` catalog -- this value is
synthesized by the agent itself, not retrieved.

P/B is deliberately NOT computed. Book value per share needs shares
outstanding, and this platform does not ingest that figure anywhere in its
schema (`Company`, `FinancialStatement`, `BalanceSheet`, and `market_data`
all lack it) -- confirmed during v1.0 implementation as a permanent
data-availability gap, not a transient per-company one. Rather than
approximate it with a non-per-share proxy (which would not be a real P/B
and could mislead on a platform where correctness is load-bearing), P/B is
disclosed as an explicit, permanent caveat on every Valuation Analyst
finding instead.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from nivesh.financials.models import FinancialStatement
from nivesh.retrieval_engine.normalization import EvidenceItem

EVIDENCE_SOURCE_COMPUTED_RATIO = "computed_ratio"

PB_UNAVAILABLE_CAVEAT = (
    "Price-to-book (P/B) could not be computed: this platform does not ingest "
    "shares-outstanding data, so book value per share is unavailable."
)


@dataclass(frozen=True)
class ComputedRatios:
    evidence_item: EvidenceItem | None
    caveats: list[str]


def compute_price_to_earnings(
    *,
    statement: FinancialStatement | None,
    latest_price: Decimal | None,
    latest_trade_date: date | None,
) -> ComputedRatios:
    caveats = [PB_UNAVAILABLE_CAVEAT]

    if latest_price is None:
        caveats.append(
            "P/E ratio could not be computed: no market price snapshot is available for this "
            "company yet. Run a market data sync to populate one."
        )
        return ComputedRatios(evidence_item=None, caveats=caveats)

    if statement is None or statement.profit_and_loss is None:
        caveats.append(
            "P/E ratio could not be computed: no financial statement with earnings data was "
            "available."
        )
        return ComputedRatios(evidence_item=None, caveats=caveats)

    eps = statement.profit_and_loss.eps_basic or statement.profit_and_loss.eps_diluted
    if eps is None or eps <= 0:
        caveats.append(
            "P/E ratio could not be computed: earnings per share is missing or non-positive "
            "for the most recent statement."
        )
        return ComputedRatios(evidence_item=None, caveats=caveats)

    pe_ratio = (latest_price / eps).quantize(Decimal("0.01"))
    date_suffix = f" as of {latest_trade_date.isoformat()}" if latest_trade_date else ""
    evidence_item = EvidenceItem(
        source_type=EVIDENCE_SOURCE_COMPUTED_RATIO,
        source_table="financial_statements",
        source_id=statement.id,
        title="Computed price-to-earnings (P/E) ratio",
        snippet=(
            f"P/E = latest price ({latest_price}) / EPS ({eps}) = {pe_ratio}, based on the "
            f"{statement.fiscal_period} FY{statement.fiscal_year} statement{date_suffix}."
        ),
        evidence_date=latest_trade_date or statement.period_end_date,
        relevance_score=1.0,
        retrieved_via=("computed",),
    )
    return ComputedRatios(evidence_item=evidence_item, caveats=caveats)
