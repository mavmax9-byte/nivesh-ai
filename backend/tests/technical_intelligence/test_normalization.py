from datetime import date, timedelta
from decimal import Decimal

import pytest

from nivesh.technical_intelligence.normalization import (
    bars_to_frame,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_obv,
    compute_rsi,
    compute_sma,
    compute_volume_sma,
)
from nivesh.technical_intelligence.providers.base import ProviderPriceBar

_BASE_DATE = date(2026, 1, 1)


def _bar(
    offset: int,
    close: float,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1000,
) -> ProviderPriceBar:
    open_price = open_ if open_ is not None else close
    return ProviderPriceBar(
        trade_date=_BASE_DATE + timedelta(days=offset),
        open=Decimal(str(open_price)),
        high=Decimal(str(high if high is not None else max(open_price, close))),
        low=Decimal(str(low if low is not None else min(open_price, close))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _constant_price_bars(
    count: int, price: float = 100.0, volume: int = 1000
) -> list[ProviderPriceBar]:
    return [_bar(i, price, volume=volume) for i in range(count)]


def _increasing_price_bars(
    count: int, start: float = 100.0, step: float = 1.0
) -> list[ProviderPriceBar]:
    return [_bar(i, start + i * step) for i in range(count)]


def _decreasing_price_bars(
    count: int, start: float = 200.0, step: float = 1.0
) -> list[ProviderPriceBar]:
    return [_bar(i, start - i * step) for i in range(count)]


def test_sma_of_constant_price_equals_that_price():
    frame = bars_to_frame(_constant_price_bars(30))
    points = compute_sma(frame, 20)

    assert len(points) == 11  # 30 - 20 + 1
    assert all(point.indicator_value == pytest.approx(100.0) for point in points)
    assert points[0].indicator_parameters == {"period": 20}


def test_sma_emits_no_points_before_window_is_full():
    frame = bars_to_frame(_constant_price_bars(19))
    assert compute_sma(frame, 20) == []


def test_sma_dates_are_the_most_recent_of_the_window():
    frame = bars_to_frame(_constant_price_bars(25))
    points = compute_sma(frame, 20)
    assert points[0].trading_date == _BASE_DATE + timedelta(days=19)
    assert points[-1].trading_date == _BASE_DATE + timedelta(days=24)


def test_ema_of_constant_price_converges_to_that_price():
    frame = bars_to_frame(_constant_price_bars(60))
    points = compute_ema(frame, 20)

    assert len(points) == 41  # 60 - 20 + 1
    assert all(point.indicator_value == pytest.approx(100.0) for point in points)


def test_rsi_of_strictly_increasing_prices_approaches_100():
    frame = bars_to_frame(_increasing_price_bars(60))
    points = compute_rsi(frame)

    assert points  # non-empty
    assert points[-1].indicator_value > 95.0


def test_rsi_of_strictly_decreasing_prices_approaches_zero():
    frame = bars_to_frame(_decreasing_price_bars(60))
    points = compute_rsi(frame)

    assert points
    assert points[-1].indicator_value < 5.0


def test_rsi_emits_no_points_before_warmup():
    frame = bars_to_frame(_constant_price_bars(13))
    assert compute_rsi(frame) == []


def test_macd_returns_three_series_with_shared_parameters():
    frame = bars_to_frame(_increasing_price_bars(80))
    macd, signal, histogram = compute_macd(frame)

    assert macd and signal and histogram
    assert macd[0].indicator_parameters == {"fast": 12, "slow": 26, "signal": 9}
    # Histogram is exactly macd - signal for matching dates.
    macd_by_date = {p.trading_date: p.indicator_value for p in macd}
    signal_by_date = {p.trading_date: p.indicator_value for p in signal}
    for point in histogram:
        expected = macd_by_date[point.trading_date] - signal_by_date[point.trading_date]
        assert point.indicator_value == pytest.approx(expected)


def test_bollinger_bands_collapse_to_price_when_volatility_is_zero():
    frame = bars_to_frame(_constant_price_bars(25))
    upper, middle, lower = compute_bollinger_bands(frame)

    assert len(upper) == len(middle) == len(lower) == 6  # 25 - 20 + 1
    for u, m, low_point in zip(upper, middle, lower, strict=True):
        assert u.indicator_value == pytest.approx(100.0)
        assert m.indicator_value == pytest.approx(100.0)
        assert low_point.indicator_value == pytest.approx(100.0)


def test_bollinger_bands_widen_with_volatility():
    bars = [_bar(i, 100.0 + (10 if i % 2 == 0 else -10)) for i in range(25)]
    frame = bars_to_frame(bars)
    upper, middle, lower = compute_bollinger_bands(frame)

    assert upper[-1].indicator_value > middle[-1].indicator_value > lower[-1].indicator_value


def test_atr_is_zero_for_flat_bars_with_no_gaps():
    bars = [_bar(i, 100.0, open_=100.0, high=100.0, low=100.0) for i in range(20)]
    frame = bars_to_frame(bars)
    points = compute_atr(frame)

    assert points
    assert all(point.indicator_value == pytest.approx(0.0) for point in points)


def test_atr_is_positive_when_true_range_exists():
    bars = [_bar(i, 100.0, open_=95.0, high=105.0, low=95.0) for i in range(20)]
    frame = bars_to_frame(bars)
    points = compute_atr(frame)

    assert points
    assert all(point.indicator_value > 0 for point in points)


def test_volume_sma_of_constant_volume_equals_that_volume():
    frame = bars_to_frame(_constant_price_bars(25, volume=5000))
    points = compute_volume_sma(frame)

    assert len(points) == 6  # 25 - 20 + 1
    assert all(point.indicator_value == pytest.approx(5000.0) for point in points)


def test_obv_first_ever_run_starts_from_zero():
    # Prices: 100, 102 (up), 101 (down), 101 (flat).
    bars = [_bar(0, 100.0), _bar(1, 102.0), _bar(2, 101.0), _bar(3, 101.0)]
    frame = bars_to_frame(bars)

    points = compute_obv(frame, starting_value=0.0, starting_date=None)

    assert len(points) == 4
    assert points[0].indicator_value == pytest.approx(0.0)  # no prior bar to compare
    assert points[1].indicator_value == pytest.approx(1000.0)  # up day: +volume
    assert points[2].indicator_value == pytest.approx(0.0)  # down day: -volume
    assert points[3].indicator_value == pytest.approx(0.0)  # flat day: unchanged


def test_obv_carries_forward_from_last_persisted_value():
    bars = [_bar(0, 100.0), _bar(1, 102.0), _bar(2, 101.0), _bar(3, 103.0)]
    frame = bars_to_frame(bars)

    # Simulate a prior run that already persisted OBV through day 1.
    points = compute_obv(frame, starting_value=500.0, starting_date=_BASE_DATE + timedelta(days=1))

    assert [p.trading_date for p in points] == [
        _BASE_DATE + timedelta(days=2),
        _BASE_DATE + timedelta(days=3),
    ]
    assert points[0].indicator_value == pytest.approx(
        500.0 - 1000.0
    )  # down day from day 1 -> day 2
    assert points[1].indicator_value == pytest.approx(
        500.0 - 1000.0 + 1000.0
    )  # up day from day 2 -> day 3


def test_obv_uses_uniform_indicator_parameters():
    frame = bars_to_frame([_bar(0, 100.0), _bar(1, 101.0)])
    points = compute_obv(frame, starting_value=0.0, starting_date=None)
    assert all(point.indicator_parameters == {} for point in points)
