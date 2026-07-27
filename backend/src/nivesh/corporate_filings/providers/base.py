"""Corporate filings metadata provider interface.

Mirrors market_data/providers/base.py and financials/providers/base.py's
adapter pattern: the application depends only on
`CorporateFilingsProvider`, never a concrete provider. Every provider
returns these normalized DTOs, never raw provider payloads, so an NSE/BSE
or commercial filings provider can replace the development provider later
without touching `CorporateFilingsService`.

Metadata only -- no provider implementation behind this interface may
return document content, only where a document can be found
(`source_url`) and facts describing it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ProviderFiling:
    exchange: str
    filing_type: str
    title: str
    reporting_period: str
    filing_date: date
    source_url: str
    checksum: str
    language: str
    document_size: int | None


class CorporateFilingsProvider(ABC):
    """Abstract contract every corporate filings provider must implement."""

    @abstractmethod
    async def get_filings(self, symbol: str) -> list[ProviderFiling]:
        """Fetch known filing metadata for a symbol, most recent first."""
        raise NotImplementedError
