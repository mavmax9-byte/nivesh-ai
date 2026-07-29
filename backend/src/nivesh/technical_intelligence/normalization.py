"""Deterministic technical indicator computation.

Pure functions -- no I/O, no side effects. Takes already-validated OHLCV
bars (see validation.py) and produces persistence-ready indicator points.
Uses pandas' `rolling()`/`ewm()` operations for the underlying arithmetic
(already a project dependency, used elsewhere for tabular numeric work,
e.g. corporate_filings' yfinance provider) -- this is plain deterministic
arithmetic, not machine learning, consistent with the "no AI/ML" constraint
on this module.

Every indicator that needs more historical bars than are available for a
given date simply has no point emitted for that date (not an error, not a
padded/estimated value) -- e.g. SMA(200) needs 200 trailing bars, so the
first 199 bars in a fetched window produce no SMA(200) point. Recursively
defined indicators (EMA, RSI's Wilder smoothing, MACD, ATR's Wilder
smoothing) are seeded using the standard textbook convention -- pandas'
`ewm(..., adjust=False)` starts the recursion from the first bar and only
emits once `min_periods` non-null observations have been seen, exactly how
every charting platform and indicator library defines these series. This
is the conventional definition, not an approximation.

OBV is fundamentally different from every other indicator here: it is a
running cumulative total from inception, not a fixed-window calculation.
Since generation recomputes over a *bounded* trailing window rather than a
company's full history (see service.py's module docstring for why), OBV
cannot be correctly derived from the window alone -- `compute_obv`
therefore accepts an explicit `starting_value`/`starting_date` (the last
already-persisted OBV point, supplied by the service) and continues the
running total from there, so OBV stays numerically correct across
generation runs regardless of the window boundary.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from nivesh.technical_intelligence.models import (
    INDICATOR_ATR_14,
    INDICATOR_BOLLINGER_LOWER,
    INDICATOR_BOLLINGER_MIDDLE,
    INDICATOR_BOLLINGER_UPPER,
    INDICATOR_EMA_20,
    INDICATOR_EMA_50,
    INDICATOR_MACD,
    INDICATOR_MACD_HISTOGRAM,
    INDICATOR_MACD_SIGNAL,
    INDICATOR_OBV,
    INDICATOR_RSI_14,
    INDICATOR_SMA_20,
    INDICATOR_SMA_50,
    INDICATOR_SMA_100,
    INDICATOR_SMA_200,
    INDICATOR_VOLUME_SMA_20,
)
from nivesh.technical_intelligence.providers.base import ProviderPriceBar

SMA_PERIODS = (20, 50, 100, 200)
EMA_PERIODS = (20, 50)
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_PERIOD = 9
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEV = 2
ATR_PERIOD = 14
VOLUME_SMA_PERIOD = 20

_SMA_INDICATOR_NAMES = {
    20: INDICATOR_SMA_20,
    50: INDICATOR_SMA_50,
    100: INDICATOR_SMA_100,
    200: INDICATOR_SMA_200,
}
_EMA_INDICATOR_NAMES = {20: INDICATOR_EMA_20, 50: INDICATOR_EMA_50}


@dataclass(frozen=True)
class ComputedIndicatorPoint:
    trading_date: date
    indicator_name: str
    indicator_parameters: dict
    indicator_value: float


def bars_to_frame(bars: list[ProviderPriceBar]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "trading_date": [bar.trade_date for bar in bars],
            "open": [float(bar.open) for bar in bars],
            "high": [float(bar.high) for bar in bars],
            "low": [float(bar.low) for bar in bars],
            "close": [float(bar.close) for bar in bars],
            "volume": [float(bar.volume) for bar in bars],
        }
    )
    return frame.sort_values("trading_date").reset_index(drop=True)


def _points_from_series(
    series: "pd.Series", dates: "pd.Series", name: str, parameters: dict
) -> list[ComputedIndicatorPoint]:
    points = []
    for value, trading_date in zip(series, dates, strict=True):
        if pd.isna(value):
            continue
        points.append(
            ComputedIndicatorPoint(
                trading_date=trading_date,
                indicator_name=name,
                indicator_parameters=parameters,
                indicator_value=float(value),
            )
        )
    return points


def compute_sma(frame: pd.DataFrame, period: int) -> list[ComputedIndicatorPoint]:
    series = frame["close"].rolling(window=period, min_periods=period).mean()
    return _points_from_series(
        series, frame["trading_date"], _SMA_INDICATOR_NAMES[period], {"period": period}
    )


def compute_ema(frame: pd.DataFrame, period: int) -> list[ComputedIndicatorPoint]:
    series = frame["close"].ewm(span=period, min_periods=period, adjust=False).mean()
    return _points_from_series(
        series, frame["trading_date"], _EMA_INDICATOR_NAMES[period], {"period": period}
    )


def compute_rsi(frame: pd.DataFrame, period: int = RSI_PERIOD) -> list[ComputedIndicatorPoint]:
    delta = frame["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing is an EMA with alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)  # no losses in the smoothing window -> RSI = 100
    return _points_from_series(rsi, frame["trading_date"], INDICATOR_RSI_14, {"period": period})


def compute_macd(
    frame: pd.DataFrame,
) -> tuple[
    list[ComputedIndicatorPoint], list[ComputedIndicatorPoint], list[ComputedIndicatorPoint]
]:
    ema_fast = frame["close"].ewm(span=MACD_FAST, min_periods=MACD_FAST, adjust=False).mean()
    ema_slow = frame["close"].ewm(span=MACD_SLOW, min_periods=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(
        span=MACD_SIGNAL_PERIOD, min_periods=MACD_SIGNAL_PERIOD, adjust=False
    ).mean()
    histogram = macd_line - signal_line
    params = {"fast": MACD_FAST, "slow": MACD_SLOW, "signal": MACD_SIGNAL_PERIOD}
    return (
        _points_from_series(macd_line, frame["trading_date"], INDICATOR_MACD, params),
        _points_from_series(signal_line, frame["trading_date"], INDICATOR_MACD_SIGNAL, params),
        _points_from_series(histogram, frame["trading_date"], INDICATOR_MACD_HISTOGRAM, params),
    )


def compute_bollinger_bands(
    frame: pd.DataFrame,
) -> tuple[
    list[ComputedIndicatorPoint], list[ComputedIndicatorPoint], list[ComputedIndicatorPoint]
]:
    middle = frame["close"].rolling(window=BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).mean()
    std = frame["close"].rolling(window=BOLLINGER_PERIOD, min_periods=BOLLINGER_PERIOD).std(ddof=0)
    upper = middle + BOLLINGER_STD_DEV * std
    lower = middle - BOLLINGER_STD_DEV * std
    params = {"period": BOLLINGER_PERIOD, "std_dev": BOLLINGER_STD_DEV}
    return (
        _points_from_series(upper, frame["trading_date"], INDICATOR_BOLLINGER_UPPER, params),
        _points_from_series(middle, frame["trading_date"], INDICATOR_BOLLINGER_MIDDLE, params),
        _points_from_series(lower, frame["trading_date"], INDICATOR_BOLLINGER_LOWER, params),
    )


def compute_atr(frame: pd.DataFrame, period: int = ATR_PERIOD) -> list[ComputedIndicatorPoint]:
    prev_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return _points_from_series(atr, frame["trading_date"], INDICATOR_ATR_14, {"period": period})


def compute_volume_sma(
    frame: pd.DataFrame, period: int = VOLUME_SMA_PERIOD
) -> list[ComputedIndicatorPoint]:
    series = frame["volume"].rolling(window=period, min_periods=period).mean()
    return _points_from_series(
        series, frame["trading_date"], INDICATOR_VOLUME_SMA_20, {"period": period}
    )


def compute_obv(
    frame: pd.DataFrame, starting_value: float, starting_date: date | None
) -> list[ComputedIndicatorPoint]:
    """Computes On Balance Volume as a running total, continuing from
    `starting_value` (the last already-persisted OBV value, or 0.0 for a
    company's first-ever generation run) -- see module docstring for why
    OBV needs this carry-forward instead of being derived from the window
    alone. Only emits points for bars strictly after `starting_date` (or
    all bars, if this is the first run and `starting_date` is None), so a
    generation run never re-emits an already-persisted OBV value.
    """
    close_diff = frame["close"].diff()
    direction = close_diff.apply(lambda d: 1 if d > 0 else (-1 if d < 0 else 0))
    signed_volume = direction * frame["volume"]
    local_cumsum = signed_volume.cumsum()

    boundary_matches = frame.index[frame["trading_date"] == starting_date] if starting_date else []
    if starting_date is not None and len(boundary_matches) > 0:
        offset = starting_value - local_cumsum.iloc[boundary_matches[0]]
    else:
        offset = starting_value

    running = local_cumsum + offset

    points = []
    for value, trading_date in zip(running, frame["trading_date"], strict=True):
        if starting_date is not None and trading_date <= starting_date:
            continue
        points.append(
            ComputedIndicatorPoint(
                trading_date=trading_date,
                indicator_name=INDICATOR_OBV,
                indicator_parameters={},
                indicator_value=float(value),
            )
        )
    return points
