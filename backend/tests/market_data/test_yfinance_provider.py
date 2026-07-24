from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from nivesh.market_data.providers.exceptions import SymbolNotFoundError
from nivesh.market_data.providers.yfinance_provider import (
    YFinanceProvider,
    _exchange_from_yahoo_symbol,
    _split_ratio_to_fraction,
    _strip_suffix,
    _to_decimal,
    _to_yahoo_symbol,
)


def test_to_yahoo_symbol_defaults_to_nse():
    assert _to_yahoo_symbol("TCS") == "TCS.NS"


def test_to_yahoo_symbol_respects_bse_exchange_code():
    assert _to_yahoo_symbol("TCS", exchange_code="BSE") == "TCS.BO"


def test_to_yahoo_symbol_passes_through_already_suffixed_symbols():
    assert _to_yahoo_symbol("TCS.NS") == "TCS.NS"


def test_exchange_from_yahoo_symbol():
    assert _exchange_from_yahoo_symbol("TCS.NS") == "NSE"
    assert _exchange_from_yahoo_symbol("TCS.BO") == "BSE"


def test_exchange_from_yahoo_symbol_falls_back_to_nse_for_unknown_suffix():
    assert _exchange_from_yahoo_symbol("AAPL") == "NSE"


def test_strip_suffix():
    assert _strip_suffix("TCS.NS") == "TCS"
    assert _strip_suffix("TCS.BO") == "TCS"


def test_to_decimal_rounds_cleanly():
    assert _to_decimal(1234.56789) == Decimal("1234.5679")


def test_split_ratio_to_fraction_two_for_one_split():
    assert _split_ratio_to_fraction(2.0) == (2, 1)


def test_split_ratio_to_fraction_reverse_split():
    assert _split_ratio_to_fraction(0.5) == (1, 2)


@pytest.mark.asyncio
async def test_get_company_metadata_maps_info_dict():
    provider = YFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "longName": "Tata Consultancy Services Limited",
        "sector": "Technology",
        "industry": "Information Technology Services",
        "currency": "INR",
    }

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        metadata = await provider.get_company_metadata("TCS")

    assert metadata.symbol == "TCS"
    assert metadata.name == "Tata Consultancy Services Limited"
    assert metadata.exchange_code == "NSE"
    assert metadata.sector == "Technology"


@pytest.mark.asyncio
async def test_get_company_metadata_raises_symbol_not_found_when_no_name():
    provider = YFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.info = {}

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        with pytest.raises(SymbolNotFoundError):
            await provider.get_company_metadata("NOPE")


@pytest.mark.asyncio
async def test_get_historical_ohlcv_maps_dataframe_rows():
    provider = YFinanceProvider()
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [104.0, 105.0],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = frame

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        bars = await provider.get_historical_ohlcv(
            "TCS", start=date(2026, 1, 1), end=date(2026, 1, 6)
        )

    assert len(bars) == 2
    assert bars[0].trade_date == date(2026, 1, 2)
    assert bars[0].close == Decimal("104.0000")
    assert bars[0].volume == 1000


@pytest.mark.asyncio
async def test_get_historical_ohlcv_raises_symbol_not_found_when_empty():
    provider = YFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        with pytest.raises(SymbolNotFoundError):
            await provider.get_historical_ohlcv(
                "NOPE", start=date(2026, 1, 1), end=date(2026, 1, 6)
            )


@pytest.mark.asyncio
async def test_get_latest_price_uses_most_recent_close():
    provider = YFinanceProvider()
    frame = pd.DataFrame(
        {"Close": [100.0, 102.5]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = frame

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        latest = await provider.get_latest_price("TCS")

    assert latest.price == Decimal("102.5000")
    assert latest.as_of == date(2026, 1, 5)


@pytest.mark.asyncio
async def test_get_corporate_actions_splits_dividends_and_splits():
    provider = YFinanceProvider()
    frame = pd.DataFrame(
        {"Dividends": [0.0, 5.0], "Stock Splits": [2.0, 0.0]},
        index=pd.to_datetime(["2026-02-01", "2026-03-01"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.actions = frame

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        actions = await provider.get_corporate_actions("TCS")

    assert len(actions) == 2
    split = next(a for a in actions if a.action_type == "split")
    dividend = next(a for a in actions if a.action_type == "dividend")
    assert split.ratio_numerator == 2
    assert split.ratio_denominator == 1
    assert dividend.dividend_amount_per_share == Decimal("5.0000")


@pytest.mark.asyncio
async def test_get_corporate_actions_returns_empty_list_when_none_exist():
    provider = YFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.actions = pd.DataFrame()

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        actions = await provider.get_corporate_actions("TCS")

    assert actions == []


@pytest.mark.asyncio
async def test_search_companies_maps_quotes():
    provider = YFinanceProvider()
    mock_search = MagicMock()
    mock_search.quotes = [
        {"symbol": "TCS.NS", "shortname": "Tata Consultancy Services"},
        {"symbol": "INFY.NS", "longname": "Infosys Limited"},
        {"symbol": None},
    ]

    with patch(
        "nivesh.market_data.providers.yfinance_provider.yf.Search", return_value=mock_search
    ):
        results = await provider.search_companies("tata")

    assert len(results) == 2
    assert results[0].symbol == "TCS"
    assert results[0].name == "Tata Consultancy Services"
    assert results[0].exchange_code == "NSE"
    assert results[1].symbol == "INFY"
    assert results[1].name == "Infosys Limited"
