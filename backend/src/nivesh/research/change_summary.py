"""Deterministic, template-based change descriptions for research versions.

Every string this module produces is built from arithmetic on watermark
values -- counts and dates already persisted in market_data. Nothing here
is generated, inferred, or summarized by a model; it is the textual
equivalent of a diff. This is what "change_summary" means throughout the
research module, and why it can exist in Sprint 3 without crossing into AI
reasoning.
"""


def build_change_summary(previous_watermark: dict | None, current_watermark: dict) -> str:
    bar_count = current_watermark["price_bar_count"]
    latest_date = current_watermark["latest_trade_date"]
    action_count = current_watermark["corporate_action_count"]

    if previous_watermark is None:
        date_clause = f" through {latest_date}" if latest_date else ""
        return (
            f"Initial research version: {bar_count} price bar(s){date_clause}, "
            f"{action_count} corporate action(s)."
        )

    parts: list[str] = []

    bar_delta = bar_count - previous_watermark.get("price_bar_count", 0)
    if bar_delta > 0:
        date_clause = f" through {latest_date}" if latest_date else ""
        parts.append(f"{bar_delta} new price bar(s){date_clause}")

    action_delta = action_count - previous_watermark.get("corporate_action_count", 0)
    if action_delta > 0:
        parts.append(f"{action_delta} new corporate action(s)")

    if not parts:
        return "Dossier metadata refreshed; no new market data since the last version."

    return "; ".join(parts) + "."
