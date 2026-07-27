"""Development corporate filings provider, backed by Yahoo Finance via
yfinance.

Chosen for the same reasons as the sibling market_data and financials
yfinance providers: no API key, reachable for NSE/BSE-listed equities,
well-suited to local development. Fully isolated behind
`CorporateFilingsProvider` -- a real NSE/BSE announcements feed or a
commercial filings provider can replace it later without touching
`CorporateFilingsService`.

yfinance has no corporate-filings/announcements endpoint for Indian
equities, so this provider derives filing *metadata* -- never document
content -- from data it does expose:

- `Ticker.get_earnings_dates()` returns each quarter's earnings
  announcement date and, for past quarters, the actually reported EPS.
  Rows with a reported EPS are treated as a `quarterly_results` filing
  having happened on that date; rows still awaiting a report (an
  estimate with no reported EPS yet) are not filings and are skipped.
- `Ticker.info["lastFiscalYearEnd"]` gives the most recently completed
  fiscal year end, used to derive one `annual_report` filing entry.

Two fields yfinance does not provide at all for this purpose:
- `reporting_period` is derived deterministically from the announcement
  date's own calendar quarter, as a proxy for the period it covers (the
  true period-end date is not exposed by this endpoint).
- `checksum` is a SHA-256 fingerprint of this provider's own stable
  metadata tuple (symbol, filing_type, reporting_period, filing_date,
  source_url) -- a deterministic content-identity stand-in, not a hash of
  the actual filed document, since this sprint never downloads documents.
  A real filings provider would supply the exchange's own checksum.
"""

import asyncio
import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import yfinance as yf

from nivesh.corporate_filings.models import (
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_QUARTERLY_RESULTS,
)
from nivesh.corporate_filings.providers.base import CorporateFilingsProvider, ProviderFiling
from nivesh.corporate_filings.providers.exceptions import FilingsProviderError

_EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_DEFAULT_EXCHANGE = "NSE"
_DEFAULT_LANGUAGE = "en"
_EARNINGS_DATES_LIMIT = 8


def _to_yahoo_symbol(symbol: str, exchange_code: str = _DEFAULT_EXCHANGE) -> str:
    upper_symbol = symbol.upper()
    if any(upper_symbol.endswith(suffix) for suffix in _EXCHANGE_SUFFIX.values()):
        return upper_symbol
    suffix = _EXCHANGE_SUFFIX.get(exchange_code.upper(), _EXCHANGE_SUFFIX[_DEFAULT_EXCHANGE])
    return f"{upper_symbol}{suffix}"


def _exchange_from_yahoo_symbol(yahoo_symbol: str) -> str:
    upper_symbol = yahoo_symbol.upper()
    for suffix, exchange_code in {v: k for k, v in _EXCHANGE_SUFFIX.items()}.items():
        if upper_symbol.endswith(suffix):
            return exchange_code
    return _DEFAULT_EXCHANGE


def _reporting_period_for_quarter(filing_date: date) -> str:
    quarter = (filing_date.month - 1) // 3 + 1
    return f"Q{quarter}FY{filing_date.year}"


def _reporting_period_for_year(fiscal_year_end: date) -> str:
    return f"FY{fiscal_year_end.year}"


def _investor_page_url(symbol: str, exchange_code: str) -> str:
    if exchange_code.upper() == "BSE":
        return f"https://www.bseindia.com/stock-share-price/{symbol.lower()}/"
    return f"https://www.nseindia.com/get-quotes/equity?symbol={symbol.upper()}"


def _compute_checksum(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8"))
    return digest.hexdigest()


class YFinanceCorporateFilingsProvider(CorporateFilingsProvider):
    async def get_filings(self, symbol: str) -> list[ProviderFiling]:
        return await asyncio.to_thread(self._fetch, symbol)

    def _fetch(self, symbol: str) -> list[ProviderFiling]:
        yahoo_symbol = _to_yahoo_symbol(symbol)
        exchange_code = _exchange_from_yahoo_symbol(yahoo_symbol)
        ticker = yf.Ticker(yahoo_symbol)

        try:
            earnings_dates = ticker.get_earnings_dates(limit=_EARNINGS_DATES_LIMIT)
        except Exception as exc:
            raise FilingsProviderError(
                f"Earnings dates fetch failed for '{symbol}': {exc}"
            ) from exc

        try:
            info = ticker.info or {}
        except Exception as exc:
            raise FilingsProviderError(f"Company info fetch failed for '{symbol}': {exc}") from exc

        filings = self._quarterly_filings(symbol, exchange_code, earnings_dates)
        annual_filing = self._annual_filing(symbol, exchange_code, info)
        if annual_filing is not None:
            filings.append(annual_filing)

        return sorted(filings, key=lambda f: f.filing_date, reverse=True)

    def _quarterly_filings(
        self, symbol: str, exchange_code: str, earnings_dates: pd.DataFrame | None
    ) -> list[ProviderFiling]:
        if earnings_dates is None or earnings_dates.empty:
            return []

        source_url = _investor_page_url(symbol, exchange_code)
        filings = []
        for filed_at, row in earnings_dates.iterrows():
            reported_eps = row.get("Reported EPS")
            if reported_eps is None or pd.isna(reported_eps):
                continue

            filing_date = filed_at.date() if hasattr(filed_at, "date") else filed_at
            reporting_period = _reporting_period_for_quarter(filing_date)
            checksum = _compute_checksum(
                symbol.upper(),
                FILING_TYPE_QUARTERLY_RESULTS,
                reporting_period,
                filing_date.isoformat(),
                source_url,
            )
            filings.append(
                ProviderFiling(
                    exchange=exchange_code,
                    filing_type=FILING_TYPE_QUARTERLY_RESULTS,
                    title=f"{symbol.upper()} Quarterly Results - {reporting_period}",
                    reporting_period=reporting_period,
                    filing_date=filing_date,
                    source_url=source_url,
                    checksum=checksum,
                    language=_DEFAULT_LANGUAGE,
                    document_size=None,
                )
            )
        return filings

    def _annual_filing(self, symbol: str, exchange_code: str, info: dict) -> ProviderFiling | None:
        raw_fiscal_year_end = info.get("lastFiscalYearEnd")
        if raw_fiscal_year_end is None:
            return None

        try:
            fiscal_year_end = datetime.fromtimestamp(raw_fiscal_year_end, tz=UTC).date()
        except (TypeError, ValueError, OSError):
            return None

        source_url = _investor_page_url(symbol, exchange_code)
        reporting_period = _reporting_period_for_year(fiscal_year_end)
        checksum = _compute_checksum(
            symbol.upper(),
            FILING_TYPE_ANNUAL_REPORT,
            reporting_period,
            fiscal_year_end.isoformat(),
            source_url,
        )
        return ProviderFiling(
            exchange=exchange_code,
            filing_type=FILING_TYPE_ANNUAL_REPORT,
            title=f"{symbol.upper()} Annual Report - {reporting_period}",
            reporting_period=reporting_period,
            filing_date=fiscal_year_end,
            source_url=source_url,
            checksum=checksum,
            language=_DEFAULT_LANGUAGE,
            document_size=None,
        )
