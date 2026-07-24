"""Normalization of provider DTOs into repository-ready persistence payloads.

Pure functions -- no I/O, no side effects. Kept separate from the
repositories (which only know how to persist) and the service (which only
orchestrates).
"""

import uuid

from nivesh.market_data.providers.base import ProviderCorporateAction, ProviderOHLCVBar


def normalize_ohlcv_bar(company_id: uuid.UUID, bar: ProviderOHLCVBar, source: str) -> dict:
    return {
        "company_id": company_id,
        "trade_date": bar.trade_date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "source": source,
    }


def normalize_corporate_action(
    company_id: uuid.UUID, action: ProviderCorporateAction, source: str
) -> dict:
    return {
        "company_id": company_id,
        "action_type": action.action_type,
        "ex_date": action.ex_date,
        "ratio_numerator": action.ratio_numerator,
        "ratio_denominator": action.ratio_denominator,
        "dividend_amount_per_share": action.dividend_amount_per_share,
        "source": source,
    }
