"""Company domain ORM models.

Slice of docs/db 01-Core-Domain.md -- Exchange and Company. A Company maps to
a single primary listing for Sprint 1 (one `symbol`, one `exchange_id`); the
full Security/Listing separation for dual-listed and non-equity instruments
(docs/db 01-Core-Domain.md sections 1.3 and 1.6) is a later extension, not
needed until multi-exchange or non-equity coverage is in scope.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base


class Exchange(Base):
    __tablename__ = "exchanges"
    __table_args__ = (UniqueConstraint("code", name="uq_exchanges_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("symbol", name="uq_companies_symbol"),
        UniqueConstraint("cin", name="uq_companies_cin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exchange_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exchanges.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    exchange: Mapped["Exchange"] = relationship()
