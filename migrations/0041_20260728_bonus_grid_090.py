"""Migration 0041 — move the 0.8x payout step from 95% to 90% realizare.

Owner decision 2026-07-28: the second payout step starts at 90% instead of
95%, so realizare in the 90-94.99% band pays 0.8x instead of 0.5x. Applied to
every agent_key in bonus_payout_grid (only '_default' exists today, but a
per-agent grid must not silently keep the old step).

Closed months are unaffected — they are read back from the frozen snapshot in
bonus_istoric.lunar_data. Open months (including past ones) recalculate live
and are repriced with the new step, as requested.

Idempotent: a 0.90 row already present for an agent_key is removed first, so
the UPDATE cannot hit UNIQUE(agent_key, threshold).
"""

VERSION = 41
NAME = "0041_20260728_bonus_grid_090"

_OLD = 0.95
_NEW = 0.90
_EPS = 1e-9


def up(conn):
    # Drop any pre-existing 0.90 row for agents that still carry the 0.95 step,
    # otherwise the UPDATE below would violate UNIQUE(agent_key, threshold).
    conn.execute(
        "DELETE FROM bonus_payout_grid "
        "WHERE ABS(threshold - ?) < ? AND agent_key IN ("
        "  SELECT agent_key FROM bonus_payout_grid WHERE ABS(threshold - ?) < ?)",
        (_NEW, _EPS, _OLD, _EPS))
    conn.execute(
        "UPDATE bonus_payout_grid SET threshold = ? WHERE ABS(threshold - ?) < ?",
        (_NEW, _OLD, _EPS))
