"""
Migration 0044 — make the bonus sales gate a per-agent setting.

Owner decision 2026-09-22: under 80% of the sales target no KPI triggers
(see docs/BUSINESS_LOGIC.md §4). The threshold is now configurable per agent
from /bonus/config instead of being fixed in code.

`bonus_config.gate_sales` was declared by migration 0011 (default 0.80) but
never read by the application. It becomes the live per-agent threshold here:
the column is added when an older DB lacks it, and NULL rows are backfilled
with the 0.80 default so every configured agent carries an explicit value.

Semantics kept by the query layer: NULL falls back to bonus_calc.SALES_GATE,
0 disables the gate for that agent. Idempotent.
"""

VERSION = 44
NAME = "0044_20260922_bonus_sales_gate"

DEFAULT_GATE = 0.80


def up(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bonus_config)").fetchall()}
    if "gate_sales" not in cols:
        conn.execute("ALTER TABLE bonus_config ADD COLUMN gate_sales REAL DEFAULT 0.80")
    conn.execute("UPDATE bonus_config SET gate_sales = ? WHERE gate_sales IS NULL",
                 (DEFAULT_GATE,))
