"""Portfolio Planner ORM models.

Per INVESTMENT_PLANNER_DESIGN.md: an AI-generated, illustrative capital
allocation the user is invited to evaluate -- not a record of real
ownership. This is deliberately a separate table pair from
`portfolios`/`holdings` (portfolios/models.py), not a reuse of them:
those tables represent a user's *actual* holdings (`quantity`,
`average_cost_price`, tenant/user-scoped behind placeholder auth); a
planned portfolio has neither a real quantity nor a real cost basis, and
per the design's own decision, needs no auth at all for this version.
Conflating the two would misrepresent an AI suggestion as an owned
position.

`PlannedPortfolio` is a **snapshot, not upsert-in-place** row -- each
generation (or regeneration) creates a new row, never overwrites a prior
one. Unlike `agent_findings`'s "a re-run supersedes the prior one, no
history" choice (PROJECT_CONTEXT.md §4 pattern 6), a planned portfolio is
closer in spirit to `ResearchVersion`: each one is a full audit-worthy
proposal a user may have reviewed and (informally) acted on, so an older
proposal must stay retrievable at its own id even after a newer one
exists. No formal version-numbering scheme is needed yet (nothing here
supersedes another specific row the way research versions chain) --
just don't upsert.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base

RISK_PROFILE_CONSERVATIVE = "conservative"
RISK_PROFILE_BALANCED = "balanced"
RISK_PROFILE_GROWTH = "growth"
VALID_RISK_PROFILES = {RISK_PROFILE_CONSERVATIVE, RISK_PROFILE_BALANCED, RISK_PROFILE_GROWTH}

HORIZON_SHORT = "short"
HORIZON_MEDIUM = "medium"
HORIZON_LONG = "long"
VALID_HORIZONS = {HORIZON_SHORT, HORIZON_MEDIUM, HORIZON_LONG}

STATUS_GENERATING = "generating"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


class PlannedPortfolio(Base):
    __tablename__ = "planned_portfolios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    capital: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    sector_exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_GENERATING)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    caveats: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    unallocated_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    evidence_sufficiency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    universe_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Read-side convenience only -- per PROJECT_CONTEXT.md §13 point 5,
    # cross-module ORM relationships are forbidden, but this one points
    # from the aggregate root to its own child table within this same
    # module, the same pattern ResearchVersion.snapshot already uses.
    holdings: Mapped[list["PlannedPortfolioHolding"]] = relationship(
        order_by="PlannedPortfolioHolding.allocated_weight.desc()"
    )


class PlannedPortfolioHolding(Base):
    __tablename__ = "planned_portfolio_holdings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_portfolios.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    # symbol/company_name/sector are denormalized off Company at generation
    # time -- the same "record what was true when this row was written"
    # idiom filing_versions.company_id already uses (PROJECT_CONTEXT.md
    # §4) -- so a planned portfolio's own explanation stays accurate even
    # if a company's sector classification changes later.
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allocated_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    allocated_weight: Mapped[float] = mapped_column(nullable=False)
    rank_score: Mapped[float] = mapped_column(nullable=False)
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    evidence_sufficiency: Mapped[str] = mapped_column(String(16), nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    weight_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    top_citation_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    top_citation_source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
