"""Pure validation rules for provider-sourced market data.

No I/O, no side effects -- kept separate from MarketDataService so the
rules are independently testable and reusable regardless of which provider
or which service method needs them.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.market_data.providers.base import ProviderCompanyMetadata, ProviderOHLCVBar


class InvalidMarketDataError(NiveshError):
    """Raised when provider data fails a validation rule that should halt a sync."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_MARKET_DATA"


def validate_company_metadata(metadata: ProviderCompanyMetadata) -> None:
    """Raises InvalidMarketDataError if metadata is unusable.

    Missing metadata means we cannot even identify what is being synced, so
    this fails the whole sync rather than being skipped.
    """
    if not metadata.symbol:
        raise InvalidMarketDataError("Company metadata is missing a symbol.")
    if not metadata.name or not metadata.name.strip():
        raise InvalidMarketDataError(f"Company metadata for '{metadata.symbol}' is missing a name.")
    if not metadata.exchange_code:
        raise InvalidMarketDataError(
            f"Company metadata for '{metadata.symbol}' is missing an exchange."
        )


def is_valid_ohlcv_bar(bar: ProviderOHLCVBar) -> bool:
    """Basic OHLCV sanity checks.

    A single bad row in a multi-year history should not fail the whole
    sync, so invalid bars are filtered out by the caller rather than
    raised on.
    """
    if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
        return False
    if bar.volume < 0:
        return False
    if bar.high < bar.low:
        return False
    if bar.high < bar.open or bar.high < bar.close:
        return False
    return not (bar.low > bar.open or bar.low > bar.close)
