"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.corporate_filings.providers.base import CorporateFilingsProvider
from nivesh.corporate_filings.providers.yfinance_provider import YFinanceCorporateFilingsProvider


def get_corporate_filings_provider() -> CorporateFilingsProvider:
    return YFinanceCorporateFilingsProvider()
