"""
Migration 0031 — Auchan (Tobra) rows: article identity by COD MARE.

Two repairs on tranzactii rows of cod_client 732 (owner report, articles
90204/90205):

1. **Un-rename rows hit by the cod_produs collision.** The July 2026 Tobra
   import replaced the file's SKU name with the Torb ERP name matched by
   cod_produs — but Tobra's numbering collides with Torb's, so e.g. the KL
   Earl Grey sale (Tobra cod 1509) was renamed to 'C.GOPLANA JELEURI
   COACAZE 190G' (Torb 1509) and misfiled under Celmar. Detect: an Auchan
   cod_produs whose rows carry BOTH the Torb ERP name for that cod AND a
   different historical Auchan name, where the two names embed DIFFERENT
   cod-mare codes (same code = legitimate ERP rename, skip) → restore the
   historical Auchan sku/furnizor.

2. **Align cod_produs to the Torb ERP code via cod mare.** Auchan rows used
   to keep Tobra's cod_produs, splitting per-article history (Stoc & Comenzi
   aggregates tranzactii by cod_produs) and breaking future-import dedup now
   that the import resolves identity by cod mare. Rows whose sku embeds a
   cod mare known to the ERP get that article's Torb cod_produs.

Mirrors etl/import_vanzari_tobra_auchan.py (extract_cod_mare /
build_cod_mare_lookup). Idempotent.
"""

import re
import sqlite3

VERSION = 31
NAME = "0031_20260707_auchan_cod_mare_identity"

AUCHAN = "732"

_CODE_EAN_RE = re.compile(r"(\d{4,6})-(\d{8,13})\)?")
_CODE_PAREN_EAN_RE = re.compile(r"\((\d{4,6})\)\s*\(\d{8,13}\)\s*$")
_TRAILING_CODE_RE = re.compile(r"[\s(](\d{4,6})\)?\s*$")


def _extract_cod_mare(sku):
    if not sku:
        return None
    s = str(sku).strip()
    m = _CODE_EAN_RE.search(s)
    if m:
        return m.group(1)
    m = _CODE_PAREN_EAN_RE.search(s)
    if m:
        return m.group(1)
    m = _TRAILING_CODE_RE.search(s)
    if m:
        return m.group(1)
    return None


def up(conn):
    non_auchan = conn.execute(
        "SELECT sku, cod_produs, MAX(data_dl) FROM tranzactii "
        "WHERE cod_client != ? AND sku IS NOT NULL GROUP BY sku, cod_produs",
        (AUCHAN,),
    ).fetchall()

    # Torb ERP: every known name per cod_produs (the buggy import used an
    # arbitrary one), and the article cod per cod mare.
    torb_names_by_cod = {}
    torb_cod_by_cm = {}
    for sku, cod, dmax in non_auchan:
        d = dmax or ""
        if cod:
            torb_names_by_cod.setdefault(str(cod), set()).add(sku)
        cm = _extract_cod_mare(sku)
        if cm:
            prev = torb_cod_by_cm.get(cm)
            if not prev or d > prev[1]:
                torb_cod_by_cm[cm] = ((sku, cod), d)

    # ── Step 1: un-rename collision-hit rows ─────────────────────────────
    hist = conn.execute(
        "SELECT cod_produs, sku, furnizor, MAX(data_dl), COUNT(*) "
        "FROM tranzactii WHERE cod_client = ? GROUP BY cod_produs, sku",
        (AUCHAN,),
    ).fetchall()
    by_cod = {}
    for cod, sku, furn, dmax, n in hist:
        by_cod.setdefault(str(cod), []).append((sku, furn, dmax or "", n))
    for cod, entries in by_cod.items():
        torb_names = torb_names_by_cod.get(cod)
        if not torb_names or len(entries) < 2:
            continue
        bad = [e for e in entries if e[0] in torb_names]
        good = [e for e in entries if e[0] not in torb_names]
        if not bad or not good:
            continue
        good.sort(key=lambda e: -e[3])
        good_sku, good_furn = good[0][0], good[0][1]
        for bad_sku, _bf, _bd, _bn in bad:
            # Same embedded cod mare on both names = an ERP rename of the
            # same article, not a collision — leave those alone.
            if _extract_cod_mare(bad_sku) == _extract_cod_mare(good_sku):
                continue
            conn.execute(
                "UPDATE tranzactii SET sku = ?, furnizor = ? "
                "WHERE cod_client = ? AND cod_produs = ? AND sku = ?",
                (good_sku, good_furn, AUCHAN, cod, bad_sku),
            )

    # ── Step 2: cod_produs -> Torb ERP cod via cod mare ─────────────────
    auchan_skus = conn.execute(
        "SELECT DISTINCT sku, cod_produs FROM tranzactii WHERE cod_client = ?",
        (AUCHAN,),
    ).fetchall()
    for sku, cod in auchan_skus:
        cm = _extract_cod_mare(sku)
        if not cm or cm not in torb_cod_by_cm:
            continue
        torb_cod = torb_cod_by_cm[cm][0][1]
        if not torb_cod or str(torb_cod) == str(cod):
            continue
        try:
            conn.execute(
                "UPDATE tranzactii SET cod_produs = ? "
                "WHERE cod_client = ? AND sku = ? AND cod_produs = ?",
                (torb_cod, AUCHAN, sku, cod),
            )
        except sqlite3.IntegrityError:
            # A row with the target (nr_dl, cod_produs, nr_factura) already
            # exists — leave this spelling on its old cod rather than lose data.
            pass
