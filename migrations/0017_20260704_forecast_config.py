"""
Migration 0017 — forecast_config key/value table with seeded defaults.

Adds a generic key/value store for forecast tuning parameters (§9 of spec)
so later forecast tasks can read/override them without schema changes.
"""

VERSION = 17
NAME = "0017_20260704_forecast_config"

DEFAULTS = {
    "fereastra_luni": 36,
    "sezonalitate_min_luni": 24,
    "indice_sezonier_min": 0.2,
    "indice_sezonier_max": 5.0,
    "prag_delistare_zile": 180,
    "prag_delistare_mult": 3,
    "coef_siguranta": 0.25,
    "perioada_acoperire_luni": 1,
    "confirmare_delistare_zile": 90,
    "taiere_inactiv_luni": 6,
    "oos_prag_pct": 50,
    "rampup_luni": 3,
    "plafon_varf_initial": 2,
    "factor_marime_min": 0.25,
    "factor_marime_max": 4.0,
}


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forecast_config (
            cheie   TEXT PRIMARY KEY,
            valoare REAL NOT NULL
        )
    """)
    for k, v in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO forecast_config (cheie, valoare) VALUES (?, ?)",
            (k, v),
        )
