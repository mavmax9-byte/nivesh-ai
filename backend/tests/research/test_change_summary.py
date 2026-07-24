from nivesh.research.change_summary import build_change_summary


def test_initial_version_with_data():
    watermark = {
        "price_bar_count": 250,
        "latest_trade_date": "2026-01-15",
        "corporate_action_count": 1,
    }
    summary = build_change_summary(None, watermark)
    assert summary == "Initial research version: 250 price bar(s) through 2026-01-15, 1 corporate action(s)."


def test_initial_version_with_no_price_history():
    watermark = {"price_bar_count": 0, "latest_trade_date": None, "corporate_action_count": 0}
    summary = build_change_summary(None, watermark)
    assert summary == "Initial research version: 0 price bar(s), 0 corporate action(s)."


def test_new_price_bars_only():
    previous = {"price_bar_count": 250, "latest_trade_date": "2026-01-15", "corporate_action_count": 1}
    current = {"price_bar_count": 262, "latest_trade_date": "2026-01-27", "corporate_action_count": 1}
    summary = build_change_summary(previous, current)
    assert summary == "12 new price bar(s) through 2026-01-27."


def test_new_corporate_actions_only():
    previous = {"price_bar_count": 250, "latest_trade_date": "2026-01-15", "corporate_action_count": 1}
    current = {"price_bar_count": 250, "latest_trade_date": "2026-01-15", "corporate_action_count": 2}
    summary = build_change_summary(previous, current)
    assert summary == "1 new corporate action(s)."


def test_new_price_bars_and_corporate_actions():
    previous = {"price_bar_count": 250, "latest_trade_date": "2026-01-15", "corporate_action_count": 1}
    current = {"price_bar_count": 255, "latest_trade_date": "2026-01-22", "corporate_action_count": 2}
    summary = build_change_summary(previous, current)
    assert summary == "5 new price bar(s) through 2026-01-22; 1 new corporate action(s)."


def test_no_change_produces_no_new_data_message():
    watermark = {"price_bar_count": 250, "latest_trade_date": "2026-01-15", "corporate_action_count": 1}
    summary = build_change_summary(watermark, dict(watermark))
    assert summary == "Dossier metadata refreshed; no new market data since the last version."


def test_previous_watermark_missing_keys_defaults_to_zero():
    previous = {}
    current = {"price_bar_count": 5, "latest_trade_date": "2026-01-05", "corporate_action_count": 0}
    summary = build_change_summary(previous, current)
    assert summary == "5 new price bar(s) through 2026-01-05."
