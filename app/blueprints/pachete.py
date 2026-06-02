import logging

from flask import Blueprint, jsonify, render_template, request

from automations._shared.prices import load_snapshot as load_prices_snapshot
from automations.pachete import pricing as pachete_pricing
from automations.pachete import storage as pachete_storage
from automations.pachete import ai_suggestions as pachete_ai


pachete_bp = Blueprint("pachete", __name__)
log = logging.getLogger(__name__)


def _load_products() -> list[dict]:
    snap = load_prices_snapshot()
    if not snap:
        return []
    return snap.get("products", []) if isinstance(snap, dict) else []


def _find_product(cod_articol: str, products: list[dict] | None = None) -> dict | None:
    products = products or _load_products()
    return next((p for p in products if str(p.get("cod_articol")) == str(cod_articol)), None)


# ── Pages ────────────────────────────────────────────────────────────────────

@pachete_bp.route("/pachete/gifting")
def gifting_page():
    return render_template("pachete/gifting.html")


@pachete_bp.route("/pachete/trendyol")
def trendyol_page():
    return render_template("pachete/trendyol.html")


# ── Shared state ─────────────────────────────────────────────────────────────

@pachete_bp.route("/api/pachete/state")
def pachete_state():
    return jsonify({
        "gifting": pachete_storage.list_gifting(),
        "trendyol": pachete_storage.list_trendyol(),
        "products_loaded": len(_load_products()),
    })


@pachete_bp.route("/api/pachete/products")
def pachete_products():
    q = (request.args.get("q") or "").strip().lower()
    limit = request.args.get("limit", 30, type=int)
    products = _load_products()
    if q:
        products = [
            p for p in products
            if q in (p.get("name") or "").lower()
            or q in str(p.get("cod_articol") or "").lower()
            or q in (p.get("brand") or "").lower()
            or q in str(p.get("ean") or "").lower()
        ]
    return jsonify({"products": products[:limit], "total": len(products)})


# ── Gifting ──────────────────────────────────────────────────────────────────

@pachete_bp.route("/api/pachete/gifting/preview", methods=["POST"])
def pachete_gifting_preview():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])
    if not items:
        return jsonify({"ok": False, "error": "Lista de produse e goala."}), 400

    products_snap = _load_products()
    enriched = []
    for item in items:
        cod = str(item.get("cod_articol", ""))
        qty = int(item.get("qty", 1))
        prod = _find_product(cod, products_snap)
        if not prod:
            return jsonify({"ok": False, "error": f"Produs negasit: {cod}"}), 400
        enriched.append({**prod, "qty": qty})

    variants = pachete_pricing.gifting_price_variants(enriched)
    return jsonify({"ok": True, "variants": variants, "products": enriched})


@pachete_bp.route("/api/pachete/gifting/save", methods=["POST"])
def pachete_gifting_save():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])
    name = (payload.get("name") or "").strip()
    theme = (payload.get("theme") or "").strip()
    final_price = payload.get("final_price")
    notes = (payload.get("notes") or "").strip()
    bundle_id = payload.get("id")
    source = payload.get("source", "manual")

    if not items:
        return jsonify({"ok": False, "error": "Lista de produse e goala."}), 400
    if not name:
        return jsonify({"ok": False, "error": "Numele pachetului e obligatoriu."}), 400

    products_snap = _load_products()
    enriched = []
    for item in items:
        cod = str(item.get("cod_articol", ""))
        qty = int(item.get("qty", 1))
        prod = _find_product(cod, products_snap)
        if not prod:
            return jsonify({"ok": False, "error": f"Produs negasit: {cod}"}), 400
        enriched.append({**prod, "qty": qty})

    totals = pachete_pricing.gifting_totals(enriched)
    ai_prices = pachete_pricing.gifting_price_variants(enriched)

    margin_pct = None
    if final_price and totals["cost"]:
        try:
            fp = float(final_price)
            margin_pct = round((fp - totals["cost"]) / fp * 100, 1) if fp > 0 else None
        except (TypeError, ValueError):
            pass

    bundle = {
        "id": bundle_id,
        "name": name,
        "theme": theme,
        "source": source,
        "products": enriched,
        "totals": totals,
        "ai_prices": ai_prices,
        "final_price": float(final_price) if final_price else None,
        "margin_pct": margin_pct,
        "status": payload.get("status", "draft"),
        "notes": notes,
    }
    saved = pachete_storage.upsert_gifting(bundle)
    return jsonify({"ok": True, "bundle": saved})


@pachete_bp.route("/api/pachete/gifting/<item_id>", methods=["DELETE"])
def pachete_gifting_delete(item_id: str):
    if not pachete_storage.delete_gifting(item_id):
        return jsonify({"ok": False, "error": "Bundle negasit."}), 404
    return jsonify({"ok": True})


@pachete_bp.route("/api/pachete/gifting/suggest", methods=["POST"])
def pachete_gifting_suggest():
    payload = request.get_json(silent=True) or {}
    n = int(payload.get("n", 8))
    products = _load_products()
    result = pachete_ai.suggest_gifting_bundles(products, n=n)
    if not result.get("ok"):
        return jsonify(result), 500

    products_snap = products
    saved_bundles = []
    for bundle_raw in result.get("bundles", []):
        enriched = []
        for item in bundle_raw.get("products", []):
            cod = str(item.get("cod_articol", ""))
            qty = int(item.get("qty", 1))
            prod = _find_product(cod, products_snap)
            if prod:
                enriched.append({**prod, "qty": qty})
        if not enriched:
            continue
        totals = pachete_pricing.gifting_totals(enriched)
        ai_prices = pachete_pricing.gifting_price_variants(enriched)
        bundle = {
            "name": bundle_raw.get("name", "Pachet AI"),
            "theme": bundle_raw.get("theme", ""),
            "rationale": bundle_raw.get("rationale", ""),
            "source": "ai_random",
            "products": enriched,
            "totals": totals,
            "ai_prices": ai_prices,
            "final_price": None,
            "margin_pct": None,
            "status": "draft",
            "notes": "",
        }
        saved = pachete_storage.upsert_gifting(bundle)
        saved_bundles.append(saved)

    return jsonify({"ok": True, "bundles": saved_bundles, "usage": result.get("usage")})


# ── Trendyol ─────────────────────────────────────────────────────────────────

@pachete_bp.route("/api/pachete/trendyol/preview", methods=["POST"])
def pachete_trendyol_preview():
    payload = request.get_json(silent=True) or {}
    cod = str(payload.get("cod_articol", ""))
    qty = int(payload.get("qty", 3))
    if not cod:
        return jsonify({"ok": False, "error": "cod_articol lipseste."}), 400

    prod = _find_product(cod)
    if not prod:
        return jsonify({"ok": False, "error": f"Produs negasit: {cod}"}), 400

    price_min = prod.get("price_min") or 0
    price_v = prod.get("price_v") or 0
    calc = pachete_pricing.trendyol_calc(price_min=price_min, price_v=price_v, qty=qty)
    suggested_qty = pachete_pricing.trendyol_suggest_qty(price_v)
    return jsonify({"ok": True, "product": prod, "calc": calc, "suggested_qty": suggested_qty})


@pachete_bp.route("/api/pachete/trendyol/save", methods=["POST"])
def pachete_trendyol_save():
    payload = request.get_json(silent=True) or {}
    cod = str(payload.get("cod_articol", ""))
    qty = int(payload.get("qty", 3))
    final_price = payload.get("final_price")
    notes = (payload.get("notes") or "").strip()
    bundle_id = payload.get("id")

    if not cod:
        return jsonify({"ok": False, "error": "cod_articol lipseste."}), 400
    if not final_price:
        return jsonify({"ok": False, "error": "Pretul final e obligatoriu."}), 400

    prod = _find_product(cod)
    if not prod:
        return jsonify({"ok": False, "error": f"Produs negasit: {cod}"}), 400

    price_min = prod.get("price_min") or 0
    price_v = prod.get("price_v") or 0
    fp = float(final_price)
    cost_real = price_min * qty + pachete_pricing.SHIPPING_TRENDYOL
    margin_total = fp - cost_real
    margin_pct = round((fp - cost_real) / fp * 100, 1) if fp > 0 else 0

    bundle = {
        "id": bundle_id,
        "ean": prod.get("ean"),
        "cod_articol": cod,
        "name": prod.get("name", ""),
        "brand": prod.get("brand", ""),
        "qty": qty,
        "price_v": price_v,
        "price_min": price_min,
        "shipping_cost": pachete_pricing.SHIPPING_TRENDYOL,
        "ai_suggested_price": payload.get("ai_suggested_price"),
        "final_price": fp,
        "margin_total": round(margin_total, 2),
        "margin_pct": margin_pct,
        "cost_real": round(cost_real, 2),
        "status": "approved",
        "notes": notes,
    }
    saved = pachete_storage.upsert_trendyol(bundle)
    return jsonify({"ok": True, "bundle": saved})


@pachete_bp.route("/api/pachete/trendyol/<item_id>", methods=["DELETE"])
def pachete_trendyol_delete(item_id: str):
    if not pachete_storage.delete_trendyol(item_id):
        return jsonify({"ok": False, "error": "Bundle negasit."}), 404
    return jsonify({"ok": True})


@pachete_bp.route("/api/pachete/trendyol/generate-all", methods=["POST"])
def pachete_trendyol_generate_all():
    products = _load_products()
    if not products:
        return jsonify({"ok": False, "error": "Snapshot de preturi gol."}), 400

    existing_codes = {str(b.get("cod_articol")) for b in pachete_storage.list_trendyol()}
    added = 0
    skipped = 0

    for prod in products:
        cod = str(prod.get("cod_articol") or "")
        if not cod or cod in existing_codes:
            skipped += 1
            continue
        price_min = prod.get("price_min") or 0
        price_v = prod.get("price_v") or 0
        if not price_v:
            skipped += 1
            continue
        qty = pachete_pricing.trendyol_suggest_qty(price_v)
        calc = pachete_pricing.trendyol_calc(price_min=price_min, price_v=price_v, qty=qty)
        ai_price = calc["psychological"]["value"]
        cost_real = calc["cost_real"]
        margin_total = ai_price - cost_real
        margin_pct = round((ai_price - cost_real) / ai_price * 100, 1) if ai_price > 0 else 0

        bundle = {
            "ean": prod.get("ean"),
            "cod_articol": cod,
            "name": prod.get("name", ""),
            "brand": prod.get("brand", ""),
            "qty": qty,
            "price_v": price_v,
            "price_min": price_min,
            "shipping_cost": pachete_pricing.SHIPPING_TRENDYOL,
            "ai_suggested_price": ai_price,
            "final_price": ai_price,
            "margin_total": round(margin_total, 2),
            "margin_pct": margin_pct,
            "cost_real": round(cost_real, 2),
            "status": "approved",
            "notes": "",
        }
        pachete_storage.upsert_trendyol(bundle)
        added += 1

    return jsonify({
        "ok": True,
        "added": added,
        "skipped": skipped,
        "total_now": len(pachete_storage.list_trendyol()),
    })


@pachete_bp.route("/api/pachete/trendyol/suggest", methods=["POST"])
def pachete_trendyol_suggest():
    payload = request.get_json(silent=True) or {}
    n = int(payload.get("n", 10))
    products = _load_products()
    result = pachete_ai.suggest_trendyol_picks(products, n=n)
    if not result.get("ok"):
        return jsonify(result), 500

    saved_bundles = []
    for sug in result.get("suggestions", []):
        cod = str(sug.get("cod_articol", ""))
        qty = int(sug.get("qty", 3))
        prod = _find_product(cod, products)
        if not prod:
            continue
        price_min = prod.get("price_min") or 0
        price_v = prod.get("price_v") or 0
        calc = pachete_pricing.trendyol_calc(price_min=price_min, price_v=price_v, qty=qty)
        ai_price = calc["psychological"]["value"]
        cost_real = calc["cost_real"]
        margin_total = ai_price - cost_real
        margin_pct = round((ai_price - cost_real) / ai_price * 100, 1) if ai_price > 0 else 0

        bundle = {
            "ean": prod.get("ean"),
            "cod_articol": cod,
            "name": prod.get("name", ""),
            "brand": prod.get("brand", ""),
            "qty": qty,
            "price_v": price_v,
            "price_min": price_min,
            "shipping_cost": pachete_pricing.SHIPPING_TRENDYOL,
            "ai_suggested_price": ai_price,
            "final_price": ai_price,
            "margin_total": round(margin_total, 2),
            "margin_pct": margin_pct,
            "cost_real": round(cost_real, 2),
            "status": "approved",
            "notes": sug.get("rationale", ""),
        }
        saved = pachete_storage.upsert_trendyol(bundle)
        saved_bundles.append(saved)

    return jsonify({"ok": True, "bundles": saved_bundles, "usage": result.get("usage")})
