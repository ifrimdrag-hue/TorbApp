"""
Migration 0018 — seed the multi-client neutral-month threshold.

Adds `prag_neutru_multi_client` (%) to forecast_config: when at least this share
of an article's listed clients sell zero in the same month, that month is marked
NEUTRAL for the whole article (Brief §4.1, level 1 heuristic) — excluded from the
pair means and pausing the delisting clock.
"""

VERSION = 18
NAME = "0018_20260704_forecast_neutral_month"

DEFAULTS = {
    "prag_neutru_multi_client": 70,
}


def up(conn):
    for k, v in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO forecast_config (cheie, valoare) VALUES (?, ?)",
            (k, v),
        )
