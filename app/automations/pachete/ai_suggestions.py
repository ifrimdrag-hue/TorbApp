"""Sugestii AI pentru pachete (gifting + Trendyol)."""

import json
import logging
import random

import anthropic

from config import settings
from automations.ai.claude_client import get_client


log = logging.getLogger(__name__)


GIFTING_SYSTEM = """Esti expert in pachete cadou pentru e-commerce romanesc.
Afacerea vinde:
- Ceaiuri premium: Basilur (Sri Lanka), Kingsleaf, Tipson, Celmar (marca proprie)
- Ciocolata fara zahar/gluten: Torras, Delaviuda, El Almendro
- Bumbac: Leonex
- Vopsea: Miss Magic Creative

Sarcina: pe baza unui catalog de produse (cu EAN, cod_articol, nume, brand, pret) iti vom \
da N propuneri RANDOM si TEMATICE de pachete gifting de 2-4 produse fiecare.

Reguli:
1. Fiecare pachet are O TEMA clara (ex: "Pachet relax matinal", "Pachet sarbatori", \
   "Pachet detox primavara", "Pachet cadou pentru ea", "Pachet weekend cozy").
2. Combinatii care merg natural: ceai + ciocolata, ceai + ceai complementar (negru + verde), \
   ceai cadou de sezon, etc. EVITA combinatii ciudate (ex: ceai + vopsea de par).
3. Foloseste produsele EXACT din catalogul oferit — referinta prin cod_articol.
4. Cantitate per produs: 1 sau 2 bucati (rareori 3 pentru produse mici).
5. Genereaza 6-10 pachete diferite (cere-ti-se variatie reala intre teme).
6. Fara cliseuri ("descopera magia", "experienta unica" etc).

Output: JSON valid conform schemei. Pretul final nu il calculezi tu — il facem noi din formula.
"""


GIFTING_SCHEMA = {
    "type": "object",
    "properties": {
        "bundles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nume comercial pachet."},
                    "theme": {"type": "string", "description": "Tema/ocazia (ex: relax, cadou femei, sarbatori)."},
                    "rationale": {"type": "string", "description": "1-2 propozitii: de ce merge combinatia asta."},
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cod_articol": {"type": "string"},
                                "qty": {"type": "integer", "description": "1-4 buc"},
                            },
                            "required": ["cod_articol", "qty"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "theme", "rationale", "products"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["bundles"],
    "additionalProperties": False,
}


TRENDYOL_SYSTEM = """Esti expert in vanzari Trendyol Romania (marketplace turcesc cu expansiune RO).
Afacerea vinde aceleasi categorii (ceaiuri, ciocolata, bumbac). Pe Trendyol se vand bine bundle-uri \
de 3-4 bucati din acelasi produs la pret atractiv (transport platit de vanzator 11 RON / comanda).

Sarcina: pe baza catalogului oferit, alege TOP N produse care:
1. Au marja buna (price_v - price_min mare in valoare ABSOLUTA, nu doar procent)
2. Sunt populare/recunoscute (Basilur are tractiune)
3. Merg bine cumparate in volum (3-4 buc) — ceaiuri de zi cu zi, ciocolate snackabile
4. EVITA produsele super-scumpe sau cu cerere de nisa

Pentru fiecare produs sugereaza cantitatea optima de bundle (3 sau 4 buc) bazat pe pret \
(price_v < 40 → 4 buc; price_v >= 40 → 3 buc, dar poti varia in functie de "feel").

Output: JSON conform schemei.
"""


TRENDYOL_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cod_articol": {"type": "string"},
                    "qty": {"type": "integer", "description": "Cantitate bundle: 3 sau 4 (uneori 2 pentru scump, 5 pentru ieftin)."},
                    "rationale": {"type": "string"},
                },
                "required": ["cod_articol", "qty", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


def _compact_catalog(products: list[dict], max_items: int = 80) -> str:
    pool = [p for p in products if p.get("emag_listed")]
    if not pool:
        pool = products
    if len(pool) > max_items:
        pool = random.sample(pool, max_items)
    lines = []
    for p in pool:
        lines.append(
            f"- cod={p.get('cod_articol')} | brand={p.get('brand', '?')} | "
            f"price_min={p.get('price_min')} price_v={p.get('price_v')} | {(p.get('name', '') or '')[:90]}"
        )
    return "\n".join(lines)


def suggest_gifting_bundles(products: list[dict], n: int = 8) -> dict:
    client = get_client()
    if not client:
        return {"ok": False, "error": "ANTHROPIC_API_KEY lipseste in .env."}
    if not products:
        return {"ok": False, "error": "Snapshot-ul de preturi e gol. Incarca-l intai."}

    catalog = _compact_catalog(products, max_items=100)
    user_text = (
        f"Genereaza {n} pachete gifting RANDOM si tematice din catalogul de mai jos.\n"
        f"Refera-te la produse DOAR prin cod_articol — nu inventa coduri.\n\n"
        f"CATALOG:\n{catalog}\n"
    )

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": GIFTING_SCHEMA},
            },
            system=[{"type": "text", "text": GIFTING_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key invalid."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limit. Asteapta cateva secunde."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Cerere invalida: {e}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Eroare API ({e.status_code}): {e.message}"}
    except Exception as e:
        log.exception("gifting AI failed")
        return {"ok": False, "error": f"Eroare: {e}"}

    parsed = _extract_json(response)
    if parsed is None:
        return {"ok": False, "error": "Raspunsul AI nu contine JSON valid."}

    return {"ok": True, "bundles": parsed.get("bundles", []), "usage": _usage(response)}


def suggest_trendyol_picks(products: list[dict], n: int = 10) -> dict:
    client = get_client()
    if not client:
        return {"ok": False, "error": "ANTHROPIC_API_KEY lipseste."}
    if not products:
        return {"ok": False, "error": "Snapshot gol."}

    enriched = []
    for p in products:
        try:
            margin_abs = (p.get("price_v") or 0) - (p.get("price_min") or 0)
        except TypeError:
            margin_abs = 0
        enriched.append({**p, "_margin_abs": margin_abs})
    enriched.sort(key=lambda x: x["_margin_abs"], reverse=True)
    top_pool = enriched[:120]
    catalog = _compact_catalog(top_pool, max_items=80)

    user_text = (
        f"Alege TOP {n} produse din catalogul de mai jos pentru bundle Trendyol (3-4 buc).\n"
        f"Refera-te DOAR prin cod_articol.\n\n"
        f"CATALOG (sortat pe marja absoluta descrescatoare):\n{catalog}\n"
    )

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=2500,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": TRENDYOL_SCHEMA},
            },
            system=[{"type": "text", "text": TRENDYOL_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key invalid."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limit."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Cerere invalida: {e}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Eroare API ({e.status_code}): {e.message}"}
    except Exception as e:
        log.exception("trendyol AI failed")
        return {"ok": False, "error": f"Eroare: {e}"}

    parsed = _extract_json(response)
    if parsed is None:
        return {"ok": False, "error": "Raspuns AI invalid."}

    return {"ok": True, "suggestions": parsed.get("suggestions", []), "usage": _usage(response)}


def _extract_json(response):
    for block in response.content:
        if block.type == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                continue
    return None


def _usage(response):
    return {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
        "model": response.model,
    }
