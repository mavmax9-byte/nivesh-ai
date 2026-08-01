"""Static index-membership seed data.

A point-in-time snapshot of the Nifty 50 constituents (NSE bare ticker
symbols, matching the format `market_data`'s `YFinanceProvider` already
expects -- see its own module docstring for the ".NS"/".BO" suffix
translation this module never has to think about). This is deliberately
**not** synced from a live index-membership provider -- index
composition changes periodically (reconstitutions), and standing up a
new external data source for that is out of scope for this version (see
INVESTMENT_PLANNER_DESIGN.md and PROJECT_CONTEXT.md §12 for the "don't
build ahead of what's asked" pattern this follows). Refreshing this list
to match a newer reconstitution is a data update, not a code change.
"""

INDEX_NIFTY50 = "NIFTY50"

NIFTY_50_SYMBOLS: tuple[str, ...] = (
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "ICICIBANK",
    "INFY",
    "HINDUNILVR",
    "ITC",
    "SBIN",
    "BHARTIARTL",
    "KOTAKBANK",
    "LT",
    "AXISBANK",
    "BAJFINANCE",
    "ASIANPAINT",
    "MARUTI",
    "SUNPHARMA",
    "TITAN",
    "ULTRACEMCO",
    "NESTLEIND",
    "WIPRO",
    "NTPC",
    "POWERGRID",
    "HCLTECH",
    "TATAMOTORS",
    "TATASTEEL",
    "JSWSTEEL",
    "ADANIENT",
    "ADANIPORTS",
    "COALINDIA",
    "ONGC",
    "BAJAJFINSV",
    "TECHM",
    "GRASIM",
    "INDUSINDBK",
    "DRREDDY",
    "CIPLA",
    "EICHERMOT",
    "APOLLOHOSP",
    "DIVISLAB",
    "BRITANNIA",
    "HEROMOTOCO",
    "BPCL",
    "SBILIFE",
    "HDFCLIFE",
    "SHRIRAMFIN",
    "TATACONSUM",
    "TRENT",
    "HINDALCO",
    "LTIM",
    "PIDILITIND",
)
