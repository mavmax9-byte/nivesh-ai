"""Development market data provider, backed by Yahoo Finance via yfinance.

Chosen as the Sprint 1 development provider because it requires no API key,
covers NSE and BSE listed equities, and is well-suited to local development
and testing. It is fully isolated behind `MarketDataProvider` -- swapping in
a commercial provider later means adding a new class here, never touching
`MarketDataService` or anything above it.

Indian equities are addressed on Yahoo Finance with an exchange suffix
(".NS" for NSE, ".BO" for BSE); callers of this provider use bare exchange
symbols (e.g. "TCS"), and the suffix translation is entirely contained in
this module.
"""

import asyncio
from datetime import date
from decimal import Decimal
from fractions import Fraction

import yfinance as yf

from nivesh.market_data.providers.base import (
    MarketDataProvider,
    ProviderCompanyMetadata,
    ProviderCompanySearchResult,
    ProviderCorporateAction,
    ProviderLatestPrice,
    ProviderOHLCVBar,
)
from nivesh.market_data.providers.exceptions import ProviderError, SymbolNotFoundError

_EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_SUFFIX_EXCHANGE = {suffix: code for code, suffix in _EXCHANGE_SUFFIX.items()}
_DEFAULT_EXCHANGE = "NSE"


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(round(float(value), 4)))


def _to_yahoo_symbol(symbol: str, exchange_code: str = _DEFAULT_EXCHANGE) -> str:
    upper_symbol = symbol.upper()
    if any(upper_symbol.endswith(suffix) for suffix in _EXCHANGE_SUFFIX.values()):
        return upper_symbol
    suffix = _EXCHANGE_SUFFIX.get(exchange_code.upper(), _EXCHANGE_SUFFIX[_DEFAULT_EXCHANGE])
    return f"{upper_symbol}{suffix}"


def _exchange_from_yahoo_symbol(yahoo_symbol: str) -> str:
    upper_symbol = yahoo_symbol.upper()
    for suffix, exchange_code in _SUFFIX_EXCHANGE.items():
        if upper_symbol.endswith(suffix):
            return exchange_code
    return _DEFAULT_EXCHANGE


def _strip_suffix(yahoo_symbol: str) -> str:
    upper_symbol = yahoo_symbol.upper()
    for suffix in _EXCHANGE_SUFFIX.values():
        if upper_symbol.endswith(suffix):
            return upper_symbol[: -len(suffix)]
    return upper_symbol


def _split_ratio_to_fraction(split_value: float) -> tuple[int, int]:
    """Yahoo's Stock Splits value is "new shares per old share" (e.g. 2.0 for
    a 2-for-1 split, 0.5 for a 1-for-2 reverse split)."""
    fraction = Fraction(split_value).limit_denominator(100)
    return fraction.numerator, fraction.denominator


class YFinanceProvider(MarketDataProvider):
    async def search_companies(self, query: str) -> list[ProviderCompanySearchResult]:
        def _search() -> list[ProviderCompanySearchResult]:
            try:
                search = yf.Search(query, max_results=10)
                quotes = search.quotes or []
            except Exception as exc:
                raise ProviderError(f"Search failed for query '{query}': {exc}") from exc

            results: list[ProviderCompanySearchResult] = []
            for quote in quotes:
                symbol = quote.get("symbol")
                if not symbol:
                    continue
                name = quote.get("shortname") or quote.get("longname") or symbol
                results.append(
                    ProviderCompanySearchResult(
                        symbol=_strip_suffix(symbol),
                        name=name,
                        exchange_code=_exchange_from_yahoo_symbol(symbol),
                    )
                )
            return results

        return await asyncio.to_thread(_search)

    async def get_company_metadata(self, symbol: str) -> ProviderCompanyMetadata:
        def _fetch() -> ProviderCompanyMetadata:
            yahoo_symbol = _to_yahoo_symbol(symbol)
            try:
                info = yf.Ticker(yahoo_symbol).info
            except Exception as exc:
                raise ProviderError(f"Metadata fetch failed for '{symbol}': {exc}") from exc

            name = info.get("longName") or info.get("shortName")
            if not name:
                raise SymbolNotFoundError(f"No metadata found for symbol '{symbol}'")

            return ProviderCompanyMetadata(
                symbol=symbol.upper(),
                name=name,
                exchange_code=_exchange_from_yahoo_symbol(yahoo_symbol),
                sector=info.get("sector"),
                industry=info.get("industry"),
                currency=info.get("currency"),
            )

        return await asyncio.to_thread(_fetch)

    async def get_historical_ohlcv(
        self, symbol: str, start: date, end: date
    ) -> list[ProviderOHLCVBar]:
        def _fetch() -> list[ProviderOHLCVBar]:
            yahoo_symbol = _to_yahoo_symbol(symbol)
            try:
                frame = yf.Ticker(yahoo_symbol).history(
                    start=start.isoformat(), end=end.isoformat(), interval="1d"
                )
            except Exception as exc:
                raise ProviderError(f"History fetch failed for '{symbol}': {exc}") from exc

            if frame is None or frame.empty:
                raise SymbolNotFoundError(f"No historical data found for symbol '{symbol}'")

            bars: list[ProviderOHLCVBar] = []
            for index, row in frame.iterrows():
                bars.append(
                    ProviderOHLCVBar(
                        trade_date=index.date(),
                        open=_to_decimal(row["Open"]),
                        high=_to_decimal(row["High"]),
                        low=_to_decimal(row["Low"]),
                        close=_to_decimal(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            return bars

        return await asyncio.to_thread(_fetch)

    async def get_latest_price(self, symbol: str) -> ProviderLatestPrice:
        def _fetch() -> ProviderLatestPrice:
            yahoo_symbol = _to_yahoo_symbol(symbol)
            try:
                frame = yf.Ticker(yahoo_symbol).history(period="5d", interval="1d")
            except Exception as exc:
                raise ProviderError(f"Latest price fetch failed for '{symbol}': {exc}") from exc

            if frame is None or frame.empty:
                raise SymbolNotFoundError(f"No price data found for symbol '{symbol}'")

            last_row = frame.iloc[-1]
            last_index = frame.index[-1]
            return ProviderLatestPrice(
                symbol=symbol.upper(),
                price=_to_decimal(last_row["Close"]),
                as_of=last_index.date(),
            )

        return await asyncio.to_thread(_fetch)

    async def get_corporate_actions(self, symbol: str) -> list[ProviderCorporateAction]:
        def _fetch() -> list[ProviderCorporateAction]:
            yahoo_symbol = _to_yahoo_symbol(symbol)
            try:
                actions_frame = yf.Ticker(yahoo_symbol).actions
            except Exception as exc:
                raise ProviderError(f"Corporate actions fetch failed for '{symbol}': {exc}") from exc

            if actions_frame is None or actions_frame.empty:
                return []

            actions: list[ProviderCorporateAction] = []
            for index, row in actions_frame.iterrows():
                ex_date = index.date()

                dividend = row.get("Dividends", 0) or 0
                if float(dividend) > 0:
                    actions.append(
                        ProviderCorporateAction(
                            action_type="dividend",
                            ex_date=ex_date,
                            ratio_numerator=None,
                            ratio_denominator=None,
                            dividend_amount_per_share=_to_decimal(dividend),
                        )
                    )

                split = row.get("Stock Splits", 0) or 0
                if float(split) > 0:
                    numerator, denominator = _split_ratio_to_fraction(float(split))
                    actions.append(
                        ProviderCorporateAction(
                            action_type="split",
                            ex_date=ex_date,
                            ratio_numerator=numerator,
                            ratio_denominator=denominator,
                            dividend_amount_per_share=None,
                        )
                    )
            return actions

        return await asyncio.to_thread(_fetch)
