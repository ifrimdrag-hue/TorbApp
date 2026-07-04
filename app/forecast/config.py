"""Typed access to forecast_config with hard defaults (§9 of spec)."""
import logging
from db import query, get_db

logger = logging.getLogger(__name__)

DEFAULTS = {
    "fereastra_luni": 36.0, "sezonalitate_min_luni": 24.0,
    "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
    "prag_delistare_zile": 180.0, "prag_delistare_mult": 3.0,
    "coef_siguranta": 0.25, "perioada_acoperire_luni": 1.0,
    "confirmare_delistare_zile": 90.0, "taiere_inactiv_luni": 6.0,
    "oos_prag_pct": 50.0, "rampup_luni": 3.0, "plafon_varf_initial": 2.0,
    "factor_marime_min": 0.25, "factor_marime_max": 4.0,
}


def get_params():
    params = dict(DEFAULTS)
    try:
        for r in query("SELECT cheie, valoare FROM forecast_config"):
            params[r["cheie"]] = float(r["valoare"])
    except Exception:
        logger.warning("forecast_config read failed; using defaults", exc_info=True)
    return params


def set_param(key, value):
    if key not in DEFAULTS:
        raise KeyError(f"unknown forecast param: {key}")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO forecast_config (cheie, valoare) VALUES (?, ?) "
            "ON CONFLICT(cheie) DO UPDATE SET valoare=excluded.valoare",
            (key, float(value)),
        )
        conn.commit()
    finally:
        conn.close()
