"""Pure validation rules for OHLCV bars feeding indicator computation.

No I/O, no side effects -- kept separate from TechnicalIntelligenceService
so the rules are independently testable, mirroring every other module's
validation.py separation. These are defense-in-depth checks: bars read
from `historical_ohlcv` have already been validated once by market_data's
own ingestion (market_data/validation.py's `is_valid_ohlcv_bar`, including
the NaN-filtering fix from v0.3), but this module does not assume upstream
data is trustworthy -- a bug elsewhere or a future data source should not
silently corrupt indicator values.

Unlike market_data's own validation (which filters out individual bad bars
so one bad row does not fail a whole multi-year sync), any structural
defect found here **halts indicator generation for the whole company**
rather than skipping the offending bar. Indicator computation is a
sequential, windowed calculation -- silently dropping one bar from the
middle of a time series would leave a gap that skews every subsequent
rolling/recursive value without any signal that something is wrong, which
is worse than simply refusing to compute until the underlying data is
fixed.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.technical_intelligence.providers.base import ProviderPriceBar

# The shortest lookback any indicator in this version needs (RSI(14) and
# ATR(14) both need 14 bars plus one prior bar for their first delta) --
# below this, indicator generation for this company is entirely pointless.
MINIMUM_BARS_FOR_ANY_INDICATOR = 15


class InsufficientHistoryError(NiveshError):
    """Raised when there are not even enough bars to compute the
    shortest-window indicator this module knows how to compute."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INSUFFICIENT_HISTORY"


class InvalidPriceHistoryError(NiveshError):
    """Raised when the fetched OHLCV history fails a structural sanity
    check that should halt indicator generation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_PRICE_HISTORY"


def validate_sufficient_history(bars: list[ProviderPriceBar]) -> None:
    if len(bars) < MINIMUM_BARS_FOR_ANY_INDICATOR:
        raise InsufficientHistoryError(
            f"Only {len(bars)} price bar(s) available; at least "
            f"{MINIMUM_BARS_FOR_ANY_INDICATOR} are required to compute any indicator."
        )


def validate_no_duplicate_timestamps(bars: list[ProviderPriceBar]) -> None:
    dates = [bar.trade_date for bar in bars]
    if len(dates) != len(set(dates)):
        raise InvalidPriceHistoryError("Price history contains duplicate trading dates.")


def validate_no_missing_values(bars: list[ProviderPriceBar]) -> None:
    for bar in bars:
        if any(value is None for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)):
            raise InvalidPriceHistoryError(
                f"Price bar for {bar.trade_date} has one or more missing OHLCV values."
            )


def validate_prices(bars: list[ProviderPriceBar]) -> None:
    for bar in bars:
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            raise InvalidPriceHistoryError(
                f"Price bar for {bar.trade_date} has a non-positive price."
            )
        if bar.high < bar.low:
            raise InvalidPriceHistoryError(f"Price bar for {bar.trade_date} has high < low.")


def validate_volumes(bars: list[ProviderPriceBar]) -> None:
    for bar in bars:
        if bar.volume < 0:
            raise InvalidPriceHistoryError(f"Price bar for {bar.trade_date} has negative volume.")
