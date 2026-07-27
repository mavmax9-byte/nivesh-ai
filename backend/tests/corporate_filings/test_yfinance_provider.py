from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from nivesh.corporate_filings.providers.exceptions import FilingsProviderError
from nivesh.corporate_filings.providers.yfinance_provider import (
    YFinanceCorporateFilingsProvider,
    _compute_checksum,
    _exchange_from_yahoo_symbol,
    _investor_page_url,
    _reporting_period_for_quarter,
    _reporting_period_for_year,
    _to_yahoo_symbol,
)


def _earnings_dates_frame(rows: list[tuple[str, float | None]]) -> pd.DataFrame:
    index = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame({"Reported EPS": [r[1] for r in rows]}, index=index)


def test_to_yahoo_symbol_defaults_to_nse():
    assert _to_yahoo_symbol("TCS") == "TCS.NS"


def test_exchange_from_yahoo_symbol():
    assert _exchange_from_yahoo_symbol("TCS.NS") == "NSE"
    assert _exchange_from_yahoo_symbol("TCS.BO") == "BSE"


def test_reporting_period_for_quarter():
    assert _reporting_period_for_quarter(date(2026, 10, 15)) == "Q4FY2026"
    assert _reporting_period_for_quarter(date(2026, 1, 20)) == "Q1FY2026"


def test_reporting_period_for_year():
    assert _reporting_period_for_year(date(2026, 3, 31)) == "FY2026"


def test_investor_page_url_nse():
    url = _investor_page_url("TCS", "NSE")
    assert url.startswith("https://www.nseindia.com/")
    assert "TCS" in url


def test_investor_page_url_bse():
    url = _investor_page_url("TCS", "BSE")
    assert url.startswith("https://www.bseindia.com/")


def test_compute_checksum_is_deterministic():
    first = _compute_checksum("TCS", "quarterly_results", "Q2FY2026")
    second = _compute_checksum("TCS", "quarterly_results", "Q2FY2026")
    assert first == second
    assert len(first) == 64


def test_compute_checksum_differs_for_different_inputs():
    assert _compute_checksum("TCS", "a") != _compute_checksum("TCS", "b")


@pytest.mark.asyncio
async def test_get_filings_returns_quarterly_filings_for_reported_earnings_only():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.return_value = _earnings_dates_frame(
        [
            ("2026-10-15", 12.5),  # reported -> a filing
            ("2026-07-15", 11.8),  # reported -> a filing
            ("2027-01-20", None),  # upcoming estimate, not yet reported -> skipped
        ]
    )
    mock_ticker.info = {}

    with patch(
        "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        filings = await provider.get_filings("TCS")

    assert len(filings) == 2
    assert all(f.filing_type == "quarterly_results" for f in filings)
    # Most recent first.
    assert filings[0].filing_date == date(2026, 10, 15)
    assert filings[0].reporting_period == "Q4FY2026"
    assert filings[1].filing_date == date(2026, 7, 15)


@pytest.mark.asyncio
async def test_get_filings_includes_annual_report_when_fiscal_year_end_present():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.return_value = _earnings_dates_frame([])
    fiscal_year_end_epoch = 1774915200  # 2026-03-31T00:00:00Z
    mock_ticker.info = {"lastFiscalYearEnd": fiscal_year_end_epoch}

    with patch(
        "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        filings = await provider.get_filings("TCS")

    assert len(filings) == 1
    assert filings[0].filing_type == "annual_report"
    assert filings[0].reporting_period == "FY2026"


@pytest.mark.asyncio
async def test_get_filings_omits_annual_report_when_fiscal_year_end_missing():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.return_value = _earnings_dates_frame([])
    mock_ticker.info = {}

    with patch(
        "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        filings = await provider.get_filings("TCS")

    assert filings == []


@pytest.mark.asyncio
async def test_get_filings_handles_none_earnings_dates_frame():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.return_value = None
    mock_ticker.info = {}

    with patch(
        "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        filings = await provider.get_filings("TCS")

    assert filings == []


@pytest.mark.asyncio
async def test_get_filings_raises_provider_error_when_earnings_dates_fetch_fails():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.side_effect = RuntimeError("network down")

    with (
        patch(
            "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker",
            return_value=mock_ticker,
        ),
        pytest.raises(FilingsProviderError),
    ):
        await provider.get_filings("TCS")


@pytest.mark.asyncio
async def test_checksums_are_stable_across_identical_calls():
    provider = YFinanceCorporateFilingsProvider()
    mock_ticker = MagicMock()
    mock_ticker.get_earnings_dates.return_value = _earnings_dates_frame([("2026-10-15", 12.5)])
    mock_ticker.info = {}

    with patch(
        "nivesh.corporate_filings.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        first = await provider.get_filings("TCS")
        second = await provider.get_filings("TCS")

    assert first[0].checksum == second[0].checksum
