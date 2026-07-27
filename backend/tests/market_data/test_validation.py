from datetime import date
from decimal import Decimal

import pytest

from nivesh.market_data.providers.base import ProviderCompanyMetadata, ProviderOHLCVBar
from nivesh.market_data.validation import (
    InvalidMarketDataError,
    is_valid_ohlcv_bar,
    validate_company_metadata,
)


def _bar(**overrides) -> ProviderOHLCVBar:
    defaults = dict(
        trade_date=date(2026, 1, 2),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=1000,
    )
    defaults.update(overrides)
    return ProviderOHLCVBar(**defaults)


def test_valid_bar_passes():
    assert is_valid_ohlcv_bar(_bar()) is True


def test_negative_open_price_is_invalid():
    assert is_valid_ohlcv_bar(_bar(open=Decimal("-1"))) is False


def test_zero_price_is_invalid():
    assert is_valid_ohlcv_bar(_bar(close=Decimal("0"))) is False


def test_high_below_low_is_invalid():
    assert is_valid_ohlcv_bar(_bar(high=Decimal("90"), low=Decimal("99"))) is False


def test_negative_volume_is_invalid():
    assert is_valid_ohlcv_bar(_bar(volume=-5)) is False


def test_close_above_high_is_invalid():
    assert is_valid_ohlcv_bar(_bar(close=Decimal("200"))) is False


def test_open_below_low_is_invalid():
    assert is_valid_ohlcv_bar(_bar(open=Decimal("50"))) is False


def test_nan_price_is_invalid_rather_than_raising():
    # Decimal("nan") is what provider-sourced NaN values round-trip to
    # (see market_data/providers/yfinance_provider.py::_to_decimal); a
    # NaN comparison via <= raises decimal.InvalidOperation instead of
    # returning False, so it must be checked explicitly.
    assert is_valid_ohlcv_bar(_bar(close=Decimal("nan"))) is False
    assert is_valid_ohlcv_bar(_bar(open=Decimal("nan"))) is False
    assert is_valid_ohlcv_bar(_bar(high=Decimal("nan"))) is False
    assert is_valid_ohlcv_bar(_bar(low=Decimal("nan"))) is False


def _metadata(**overrides) -> ProviderCompanyMetadata:
    defaults = dict(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_code="NSE",
        sector="Technology",
        industry="IT Services",
        currency="INR",
    )
    defaults.update(overrides)
    return ProviderCompanyMetadata(**defaults)


def test_validate_company_metadata_passes_for_complete_metadata():
    validate_company_metadata(_metadata())  # should not raise


def test_validate_company_metadata_rejects_missing_name():
    with pytest.raises(InvalidMarketDataError):
        validate_company_metadata(_metadata(name=""))


def test_validate_company_metadata_rejects_missing_symbol():
    with pytest.raises(InvalidMarketDataError):
        validate_company_metadata(_metadata(symbol=""))


def test_validate_company_metadata_rejects_missing_exchange():
    with pytest.raises(InvalidMarketDataError):
        validate_company_metadata(_metadata(exchange_code=""))
