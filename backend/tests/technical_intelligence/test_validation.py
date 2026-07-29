from datetime import date, timedelta
from decimal import Decimal

import pytest

from nivesh.technical_intelligence.providers.base import ProviderPriceBar
from nivesh.technical_intelligence.validation import (
    InsufficientHistoryError,
    InvalidPriceHistoryError,
    validate_no_duplicate_timestamps,
    validate_no_missing_values,
    validate_prices,
    validate_sufficient_history,
    validate_volumes,
)

_BASE_DATE = date(2026, 1, 1)


def _bar(offset: int = 0, **overrides) -> ProviderPriceBar:
    defaults: dict = dict(
        trade_date=_BASE_DATE + timedelta(days=offset),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("102.00"),
        volume=10_000,
    )
    defaults.update(overrides)
    return ProviderPriceBar(**defaults)


def _bars(count: int) -> list[ProviderPriceBar]:
    return [_bar(offset=i) for i in range(count)]


def test_sufficient_history_passes_with_enough_bars():
    validate_sufficient_history(_bars(15))  # should not raise


def test_sufficient_history_rejects_too_few_bars():
    with pytest.raises(InsufficientHistoryError):
        validate_sufficient_history(_bars(14))


def test_no_duplicate_timestamps_passes_for_unique_dates():
    validate_no_duplicate_timestamps(_bars(20))  # should not raise


def test_no_duplicate_timestamps_rejects_duplicates():
    bars = _bars(5)
    bars[3] = _bar(offset=1)  # duplicate of bars[1]'s date
    with pytest.raises(InvalidPriceHistoryError):
        validate_no_duplicate_timestamps(bars)


def test_no_missing_values_passes_for_complete_bars():
    validate_no_missing_values(_bars(5))  # should not raise


def test_no_missing_values_rejects_none_close():
    bars = _bars(3)
    bars[1] = _bar(offset=1, close=None)
    with pytest.raises(InvalidPriceHistoryError):
        validate_no_missing_values(bars)


def test_prices_passes_for_sane_bar():
    validate_prices(_bars(3))  # should not raise


def test_prices_rejects_non_positive_open():
    bars = [_bar(open=Decimal("0"))]
    with pytest.raises(InvalidPriceHistoryError):
        validate_prices(bars)


def test_prices_rejects_high_below_low():
    bars = [_bar(high=Decimal("90.00"), low=Decimal("95.00"))]
    with pytest.raises(InvalidPriceHistoryError):
        validate_prices(bars)


def test_volumes_passes_for_non_negative_volume():
    validate_volumes(_bars(3))  # should not raise


def test_volumes_rejects_negative_volume():
    bars = [_bar(volume=-1)]
    with pytest.raises(InvalidPriceHistoryError):
        validate_volumes(bars)
