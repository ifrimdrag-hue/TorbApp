"""Verifica fezabilitatea stocului pentru o campanie folosind ultimul snapshot.

Match-uirea se face robust pe TREI chei posibile (in ordine de incercare):
  1. sku (cod intern din raport)
  2. codmare (cu si fara sufix -XX)
  3. ean (cod de bare)

Daca oricare din ele match-uieste, gasim produsul. Asta acopera cazuri:
  - Basilur: codmare cu sufix -00 (71395-00) — diferit de Shopify SKU pe care il avem
  - Delaviuda: codmare cu 4 cifre (1758) — total alt sistem
  - Produse cu acelasi cod intern dar codmare diferit
"""

from .._shared.snapshot import load_snapshot
from .models import Campaign


def _norm(value) -> str | None:
    """Normalizeaza un cod: strip apostrof + strip sufix -XX."""
    if value is None:
        return None
    s = str(value).strip().lstrip("'")
    if "-" in s:
        parts = s.rsplit("-", 1)
        if parts[1].isdigit() and len(parts[1]) <= 3:
            s = parts[0]
    return s.strip() or None


def _build_lookup(snapshot: dict) -> dict[str, list[dict]]:
    """Construieste un dict cu toate cheile de cautare normalizate → lista de randuri."""
    lookup: dict[str, list[dict]] = {}
    for row in snapshot.get("rows", []):
        for key_field in ("sku", "codmare", "ean"):
            v = row.get(key_field)
            if v:
                # Adaugam si valoarea raw, si valoarea normalizata
                for k in {str(v).strip(), _norm(v) or ""}:
                    if k:
                        lookup.setdefault(k, []).append(row)
    return lookup


def _find_product(p, lookup: dict[str, list[dict]]) -> dict | None:
    """Cauta produsul in snapshot folosind toate cheile disponibile."""
    candidates: list[str] = []
    for key_val in (p.sku, p.codmare, p.ean):
        if key_val:
            candidates.append(str(key_val).strip())
            n = _norm(key_val)
            if n and n != str(key_val).strip():
                candidates.append(n)
    for cand in candidates:
        if cand in lookup and lookup[cand]:
            return lookup[cand][0]
    return None


def validate(campaign: Campaign) -> dict:
    snapshot = load_snapshot()
    if not snapshot:
        return {
            "ok": False,
            "error": (
                "Nu exista raport de stocuri salvat. "
                "Mergi la Stocuri → eMAG sau Shopify si ruleaza o sincronizare."
            ),
            "items": [],
        }

    lookup = _build_lookup(snapshot)

    items = []
    for p in campaign.products:
        record = _find_product(p, lookup)

        if record is None:
            items.append({
                "sku": p.sku,
                "codmare": p.codmare,
                "name": p.name,
                "qty_needed": p.qty_needed,
                "stock_available": None,        # None = NEGASIT (vs 0 = match cu stoc 0)
                "coverage": None,
                "status": "not_found",
                "matched_via": None,
            })
            continue

        stock = int(record["qty"])
        # Determina pe ce cheie a match-uit
        matched_via = None
        for key_field in ("sku", "codmare", "ean"):
            if record.get(key_field):
                if (p.sku and (str(record[key_field]) == p.sku or _norm(record[key_field]) == _norm(p.sku))) \
                   or (p.codmare and (str(record[key_field]) == p.codmare or _norm(record[key_field]) == _norm(p.codmare))) \
                   or (p.ean and str(record[key_field]) == p.ean):
                    matched_via = key_field
                    break

        if p.qty_needed is None or p.qty_needed <= 0:
            status = "info"
            coverage = None
        else:
            coverage = stock / p.qty_needed if p.qty_needed > 0 else None
            if coverage >= 1.5:
                status = "sufficient"
            elif coverage >= 1.0:
                status = "tight"
            else:
                status = "insufficient"

        items.append({
            "sku": p.sku,
            "codmare": p.codmare,
            "name": p.name,
            "qty_needed": p.qty_needed,
            "stock_available": stock,
            "coverage": round(coverage, 2) if coverage is not None else None,
            "status": status,
            "matched_via": matched_via,
        })

    counts = {
        "sufficient":   sum(1 for x in items if x["status"] == "sufficient"),
        "tight":        sum(1 for x in items if x["status"] == "tight"),
        "insufficient": sum(1 for x in items if x["status"] == "insufficient"),
        "info":         sum(1 for x in items if x["status"] == "info"),
        "not_found":    sum(1 for x in items if x["status"] == "not_found"),
    }

    overall = "ok"
    if counts["not_found"] > 0:
        overall = "warning"  # nu e blocant, dar trebuie verificat
    if counts["insufficient"] > 0:
        overall = "blocked"
    elif counts["tight"] > 0 and overall == "ok":
        overall = "warning"

    return {
        "ok": True,
        "snapshot_uploaded_at": snapshot["uploaded_at"],
        "snapshot_source": snapshot.get("source_filename", ""),
        "overall": overall,
        "counts": counts,
        "items": items,
    }
