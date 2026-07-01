"""Generator AI pentru propuneri de campanii.

Foloseste Claude opus-4-7 cu adaptive thinking pentru a propune N campanii
complete (cu produse reale din raport, mecanici, buget, task-uri sugerate).
"""

import json
import logging
from datetime import date

import anthropic

from config import settings
from .._shared.prices import load_snapshot as load_prices_snapshot
from .._shared.snapshot import load_snapshot as load_stock_snapshot
from .claude_client import get_client


log = logging.getLogger(__name__)


SYSTEM_PROMPT_CAMPAIGN_GEN = """Esti un strateg de marketing senior pentru o afacere e-commerce romaneasca.

BRAND-URI ACTIVE in portofoliu:
- Basilur (ceaiuri premium, gift-friendly Tea Books)
- Kingsleaf (ceaiuri)
- Tipson (ceaiuri)
- Organsia (ceaiuri bio)
- Torras (ciocolata fara zahar/gluten — health niche)
- Celmar (marca proprie ceai — entry price)
- Delaviuda + El Almendro (ciocolata praline premium din Spania)
- Leonex (produse din bumbac organic)
- Miss Magic Creative (vopsea de par)

CANALE de vanzare: Shopify + eMAG (preturi & pachete)
CANALE de comunicare: Instagram + Facebook (postari)

TIPURI DE CAMPANII:
- promo: reducere clasica
- gifting: pachete cadou (Mama, Tata, Craciun, etc)
- lansare: produse noi
- sezonier: legate de un sezon/eveniment
- giveaway: concurs cu inscriere

REGULI cand generezi propuneri:
1. **Bugetul total** alocat de user trebuie respectat — suma bugetelor pe campanii = total exact
2. **Datele** trebuie sa fie in perioada ceruta de user
3. **Mecanica** trebuie aliniata cu campul `discount`:
   - "Reducere 20%" → discount.type=percent_off, value=20
   - "Pret fix 99 RON" → discount.type=fixed_price, value=99
   - "2+1" → discount.type=percent_off, value=33 (echivalent ~33%)
   - "fara discount" → discount.type=none, value=null
4. **Produse**: alege STRICT din lista furnizata de user (cu sku/codmare/ean reale). Nu inventa produse.
   REGULI STRICTE DE POTRIVIRE (NU LE INCALCA NICIODATA):
   a) Daca numele campaniei contine un brand (ex: "Basilur Tea Giveaway"), TOATE produsele
      din campanie TREBUIE sa fie din acel brand. Fara exceptii. Fara "premii complementare"
      din alt brand. Fara amestec.
   b) Daca numele contine 2 branduri (ex: "Delaviuda & Torras"), produsele TREBUIE sa fie
      din AMBELE branduri (cel putin 1 produs din fiecare).
   c) Daca campania e tematica (ex: "ceaiuri de toamna"), categoria produselor TREBUIE
      sa se potriveasca temei (numai ceaiuri, nu ciocolata).
   d) Daca in catalog NU exista produse potrivite pentru tema/brand-urile pe care voiai
      sa le folosesti, **SCHIMBA numele si tema campaniei** ca sa se potriveasca cu ce
      este disponibil. NU forta combinatii gresite.
   e) Minim 3 produse per campanie (cu exceptia giveaway-urilor unde poate fi 1 produs).
   f) Atentie la atributul `brand` din lista — branduri pot fi listate combinat ca
      "Basilur-Organsia" sau "Delaviuda El Almendro" — verifica baza brand-ului
      cand cauti potrivirea (ex: "Basilur" se gaseste in "Basilur-Organsia").
5. **Diversitate**: campaniile sa fie complementare, nu sa se canibalizeze. Tip-uri diferite, audiente diferite.
6. **Sezonalitate RO**:
   - Mai: Ziua Mamei (3 mai), tranzitie primavara→vara, terase deschise
   - Iunie: Ziua Copilului (1 iunie), inceput vara
   - Iulie-August: vacante, picnic, hidratare
   - Septembrie: back-to-school, toamna
   - Octombrie-Noiembrie: Halloween, Black Friday
   - Decembrie: Craciun gifting peak
7. **Task-uri**: pentru fiecare campanie, sugereaza 4-7 task-uri concrete (brief, foto, ads setup, etc) cu deadline-uri realiste.
8. **Strategy rationale**: explica de ce ai ales tipul si timing-ul respectiv (1-2 propozitii).

Output: JSON valid conform schemei. Limba: romana fara diacritice.
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Scurta sinteza strategica (2-3 propozitii) despre toate campaniile propuse.",
        },
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["promo", "gifting", "lansare", "sezonier", "giveaway"]},
                    "mechanic": {"type": "string"},
                    "date_start": {"type": "string", "description": "Format YYYY-MM-DD"},
                    "date_end": {"type": "string", "description": "Format YYYY-MM-DD"},
                    "channels": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["shopify", "emag", "instagram", "facebook"]},
                    },
                    "discount": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["none", "percent_off", "fixed_off", "fixed_price"]},
                            "value": {"type": ["number", "null"]},
                        },
                        "required": ["type", "value"],
                        "additionalProperties": False,
                    },
                    "budget_alloc": {"type": "number"},
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "codmare": {"type": ["string", "null"]},
                                "ean": {"type": ["string", "null"]},
                                "name": {"type": "string"},
                                "qty_needed": {"type": ["integer", "null"]},
                            },
                            "required": ["sku", "codmare", "ean", "name", "qty_needed"],
                            "additionalProperties": False,
                        },
                    },
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                                "deadline": {"type": "string", "description": "Format YYYY-MM-DD"},
                                "assignee": {"type": "string"},
                                "assignee_type": {"type": "string", "enum": ["internal", "external"]},
                            },
                            "required": ["title", "priority", "deadline", "assignee", "assignee_type"],
                            "additionalProperties": False,
                        },
                    },
                    "notes": {"type": "string", "description": "Note strategice si KPI tinta."},
                    "strategy_rationale": {"type": "string", "description": "De ce aceasta campanie acum."},
                },
                "required": ["name", "type", "mechanic", "date_start", "date_end", "channels",
                             "discount", "budget_alloc", "products", "tasks", "notes", "strategy_rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "proposals"],
    "additionalProperties": False,
}


def _brand_matches(catalog_brand: str, focus: str) -> bool:
    """Match laxat — 'Basilur' se gaseste in 'Basilur-Organsia'."""
    if not catalog_brand or not focus:
        return False
    return focus.lower().strip() in catalog_brand.lower().strip()


def _build_products_context(brands_focus: list[str] | None = None,
                            max_per_brand: int = 80) -> str:
    """Construieste un context cu produsele disponibile (din pricelist + stock snapshot)."""
    prices = load_prices_snapshot()
    stocks = load_stock_snapshot()

    if not prices:
        return "(nu exista lista de preturi incarcata)"

    # Build stock lookup by EAN, codmare, sku
    stock_lookup = {}
    for r in (stocks or {}).get("rows", []):
        for k in (r.get("sku"), r.get("codmare"), r.get("ean")):
            if k:
                stock_lookup[str(k)] = r["qty"]

    by_brand: dict[str, list[dict]] = {}
    for p in prices.get("products", []):
        brand = p.get("brand", "Altele")
        if brands_focus:
            # match permisiv: "Basilur" se gaseste in "Basilur-Organsia"
            if not any(_brand_matches(brand, f) for f in brands_focus):
                continue
        by_brand.setdefault(brand, []).append(p)

    lines = []
    for brand, products in by_brand.items():
        lines.append(f"\n## {brand} ({len(products)} produse)")
        # Limita per brand pentru a nu exploda contextul
        for p in products[:max_per_brand]:
            cod = p.get("cod_articol") or "?"
            ean = p.get("ean") or "?"
            name = (p.get("name") or "")[:100]
            price_v = p.get("price_v")
            stock = stock_lookup.get(str(cod)) or stock_lookup.get(str(ean), "?")
            lines.append(f"  - cod_articol={cod} ean={ean} | brand={brand} | {name} | pret_v={price_v} RON | stoc={stock}")
        if len(products) > max_per_brand:
            lines.append(f"  ... si inca {len(products) - max_per_brand} produse din acelasi brand (NU sunt afisate aici, dar exista in catalog)")

    return "\n".join(lines)


def validate_proposal_brands(proposal: dict, products_catalog: list[dict]) -> list[str]:
    """Verifica daca produsele dintr-o propunere se potrivesc cu numele campaniei.
    Returneaza lista de warning-uri (goala daca totul e ok).
    """
    name = (proposal.get("name") or "").lower()
    warnings = []
    products = proposal.get("products") or []

    if not products:
        warnings.append("Campania nu are produse alocate.")
        return warnings

    # Build lookup cod_articol -> brand
    code_to_brand = {str(p.get("cod_articol")): p.get("brand", "") for p in products_catalog}

    # Detectam brand-urile mentionate in numele campaniei
    known_brand_keywords = ["basilur", "kingsleaf", "tipson", "organsia", "torras", "celmar",
                            "delaviuda", "almendro", "leonex", "miss magic"]
    mentioned_brands = [b for b in known_brand_keywords if b in name]

    if mentioned_brands:
        # Toate produsele trebuie sa fie din brand-urile mentionate
        for prod in products:
            cod = str(prod.get("codmare") or prod.get("sku") or "")
            actual_brand = (code_to_brand.get(cod) or "").lower()
            if not any(mb in actual_brand for mb in mentioned_brands):
                warnings.append(
                    f"Produsul '{(prod.get('name') or '')[:50]}' (cod {cod}) "
                    f"are brand '{actual_brand or '?'}' care nu se potriveste cu "
                    f"campania ce mentioneaza: {', '.join(mentioned_brands)}"
                )

        # Daca s-au mentionat 2+ branduri, fiecare TREBUIE sa apara macar 1 data
        if len(mentioned_brands) >= 2:
            present = set()
            for prod in products:
                cod = str(prod.get("codmare") or prod.get("sku") or "")
                actual = (code_to_brand.get(cod) or "").lower()
                for mb in mentioned_brands:
                    if mb in actual:
                        present.add(mb)
            missing = set(mentioned_brands) - present
            if missing:
                warnings.append(f"Campania mentioneaza {', '.join(missing)} dar niciun produs nu e din acel brand.")

    return warnings


def generate_campaign_proposals(
    period_start: str,
    period_end: str,
    total_budget: float,
    num_campaigns: int,
    goal: str,
    brands_focus: list[str] | None = None,
    notes: str = "",
) -> dict:
    """Genereaza N campanii ca propuneri (status=draft pana cand userul le salveaza).

    Returns dict cu: ok, data (proposals + summary), usage, error
    """
    client = get_client()
    if not client:
        return {
            "ok": False,
            "error": "ANTHROPIC_API_KEY nu este setat in .env.",
        }

    if num_campaigns < 1 or num_campaigns > 5:
        return {"ok": False, "error": "Numar campanii: intre 1 si 5."}

    if total_budget <= 0:
        return {"ok": False, "error": "Buget total trebuie > 0."}

    # Build product context
    products_ctx = _build_products_context(brands_focus)

    user_msg = f"""Genereaza {num_campaigns} campanii complete pentru:

PERIOADA: {period_start} → {period_end}
BUGET TOTAL DISPONIBIL: {total_budget} RON (suma bugetelor campaniilor = exact aceasta valoare)
DATA CURENTA: {date.today().isoformat()}

OBIECTIV STRATEGIC:
{goal}

BRAND-URI FOCUS: {", ".join(brands_focus) if brands_focus else "libertate totala — alege ce se potriveste"}

INDICATII SUPLIMENTARE:
{notes or "(fara — alege liber)"}

PRODUSE DISPONIBILE in portofoliul curent (alege STRICT de aici, nu inventa):
{products_ctx}

Genereaza pachetul JSON conform schemei. Fiecare campanie complet detaliata cu produse reale, task-uri sugerate, mecanica clara si rationale."""

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT_CAMPAIGN_GEN,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key invalid. Verifica .env."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limit. Asteapta cateva secunde."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Cerere invalida: {e}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Eroare API ({e.status_code}): {e.message}"}
    except Exception as e:
        log.exception("AI campaign generation failed")
        return {"ok": False, "error": f"Eroare neasteptata: {e}"}

    parsed = None
    for block in response.content:
        if block.type == "text":
            try:
                parsed = json.loads(block.text)
                break
            except json.JSONDecodeError as e:
                log.error("Invalid JSON in campaign AI response: %s — %.200s", e, block.text)
                continue

    if parsed is None:
        return {"ok": False, "error": "Raspunsul AI nu contine JSON valid."}

    # Post-validation: pentru fiecare propunere, verifica daca brandurile produselor
    # se potrivesc cu numele campaniei. Adauga warnings vizibile in UI.
    catalog_products = (load_prices_snapshot() or {}).get("products", [])
    for prop in parsed.get("proposals", []):
        warns = validate_proposal_brands(prop, catalog_products)
        if warns:
            prop["_warnings"] = warns

    return {
        "ok": True,
        "data": parsed,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "model": response.model,
        },
    }
