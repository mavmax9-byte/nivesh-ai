"""Technical Intelligence Engine ORM models.

Stores deterministic technical indicators computed from already-persisted
OHLCV data (market_data's `historical_ohlcv` table) -- no trading signals,
no forecasting, no AI. `TechnicalIndicator` is a narrow entity-attribute-
value table (one row per company + trading_date + indicator_name) rather
than one wide row per date with a column per indicator, because the set of
indicators computed here is expected to keep growing (this sprint alone
computes 16 series across 4 categories) and an EAV shape lets a new
indicator be added purely additively -- a new `indicator_name` value, never
a schema migration.

No version-history table, following the same "no versioning needed"
precedent as document_intelligence's `DocumentExtraction` and
news_intelligence's `NewsArticle`: a technical indicator value for a given
(company, date, indicator) is a pure function of OHLCV history up to that
date, so recomputing it is idempotent -- generation upserts
(`ON CONFLICT DO UPDATE`, the same idiom market_data's own `bulk_upsert`
uses) rather than versioning changes.

`indicator_parameters` (JSONB) fully specifies the exact configuration used
(e.g. `{"period": 20}` for SMA, `{"fast": 12, "slow": 26, "signal": 9}` for
MACD) even where `indicator_name` alone is unambiguous today (this version
computes exactly one MACD/Bollinger configuration) -- this keeps the
parameters queryable/inspectable without parsing them back out of the name,
and means a future second parameterization of the same base indicator only
needs a new `indicator_name`, not a schema change.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nivesh.core.db import Base

# Trend
INDICATOR_SMA_20 = "sma_20"
INDICATOR_SMA_50 = "sma_50"
INDICATOR_SMA_100 = "sma_100"
INDICATOR_SMA_200 = "sma_200"
INDICATOR_EMA_20 = "ema_20"
INDICATOR_EMA_50 = "ema_50"

# Momentum
INDICATOR_RSI_14 = "rsi_14"
INDICATOR_MACD = "macd"
INDICATOR_MACD_SIGNAL = "macd_signal"
INDICATOR_MACD_HISTOGRAM = "macd_histogram"

# Volatility
INDICATOR_BOLLINGER_UPPER = "bollinger_upper"
INDICATOR_BOLLINGER_MIDDLE = "bollinger_middle"
INDICATOR_BOLLINGER_LOWER = "bollinger_lower"
INDICATOR_ATR_14 = "atr_14"

# Volume
INDICATOR_OBV = "obv"
INDICATOR_VOLUME_SMA_20 = "volume_sma_20"

VALID_INDICATOR_NAMES = {
    INDICATOR_SMA_20,
    INDICATOR_SMA_50,
    INDICATOR_SMA_100,
    INDICATOR_SMA_200,
    INDICATOR_EMA_20,
    INDICATOR_EMA_50,
    INDICATOR_RSI_14,
    INDICATOR_MACD,
    INDICATOR_MACD_SIGNAL,
    INDICATOR_MACD_HISTOGRAM,
    INDICATOR_BOLLINGER_UPPER,
    INDICATOR_BOLLINGER_MIDDLE,
    INDICATOR_BOLLINGER_LOWER,
    INDICATOR_ATR_14,
    INDICATOR_OBV,
    INDICATOR_VOLUME_SMA_20,
}


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "trading_date",
            "indicator_name",
            name="uq_technical_indicators_company_date_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    indicator_name: Mapped[str] = mapped_column(String(32), nullable=False)
    indicator_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    indicator_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    calculation_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
