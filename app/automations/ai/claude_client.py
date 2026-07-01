"""Client Claude API pentru generarea de continut marketing pe campanii.

Foloseste:
  - claude-opus-4-7 (default — cel mai capabil pentru content + analiza vizuala)
  - adaptive thinking (Claude decide cand si cat sa gandeasca)
  - vision (analiza poza furnizata)
  - prompt caching pe system prompt-ul stabil (reduce costul cu ~90%)
  - structured outputs (JSON schema garantat)
"""

import base64
import json
import logging

import anthropic

from config import settings

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Esti asistent expert de marketing pentru o afacere e-commerce romaneasca \
care vinde:
- Ceaiuri premium: Basilur (Sri Lanka), Kingsleaf, Tipson, Organsia
- Ciocolata fara zahar/gluten: Torras, Delaviuda, El Almendro (Spania)
- Marca proprie ceai: Celmar
- Produse din bumbac: Leonex
- Vopsea de par: Miss Magic Creative

Canale active:
- eMAG Marketplace (RO) — focus pe pret/oferte
- Shopify — store propriu
- Instagram + Facebook — postari brand, lifestyle, oferte

Reguli:
1. **Limba**: TOATA generarea in romana corecta gramatical, fara diacritice obligatorii.
2. **Ton**: cald, profesionist, orientat catre rezultat comercial — nu vanity.
3. **Sezon**: tine cont de momentul anului (sarbatori RO: Martisor, Paste, Mama, Vara, \
   Craciun, Black Friday).
4. **Lungime**:
   - description_long: 150-300 cuvinte, structurata cu paragrafe scurte.
   - instagram_caption: 80-150 cuvinte + 5-10 hashtag-uri RO la final.
   - facebook_caption: 100-200 cuvinte, ton mai narativ, cu emoji moderat.
5. **Hero products**: alege 2-4 produse din lista campaniei pe care le evidentiezi cel mai \
   mult (cele mai iconice, sezoniere, sau cu marja buna).
6. **Posting plan**: 3-5 momente cheie (teaser, lansare, reminder mid, ultima zi). \
   Specifica DATA, CANAL, MESAJ scurt.
7. **Warnings**: lista de avertismente ale tale — chestii pe care marketing-managerul \
   trebuie sa le verifice (ex: "Stoc mic la X — risc rupere", "Mecanica 2+1 are nevoie \
   de ajustare in CMS Shopify", "Conflict cu campania anterioara X").
8. **Image analysis** (daca e poza): scurt rezumat a ce vezi in poza si cum o folosim \
   in campanie. Daca nu e poza, lasa stringul gol.

Output: JSON valid, conform schemei. Nicio explicatie inainte sau dupa JSON.
"""


def get_client() -> anthropic.Anthropic | None:
    """Returneaza client-ul Anthropic sau None daca nu e configurat key-ul."""
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def _format_discount(d: dict | None) -> str:
    if not d or d.get("type") == "none":
        return "fara reducere"
    t = d.get("type")
    v = d.get("value")
    if t == "percent_off":
        return f"-{v}%"
    if t == "fixed_off":
        return f"-{v} RON din pret"
    if t == "fixed_price":
        return f"{v} RON pret nou"
    return "-"


def _format_products(products: list[dict]) -> str:
    if not products:
        return "(niciun produs adaugat in campanie)"
    lines = []
    for p in products[:30]:  # limitam la 30 ca sa nu explodeze contextul
        sku = p.get("sku", "?")
        cm = p.get("codmare") or "—"
        name = p.get("name") or ""
        qty = p.get("qty_needed")
        qty_str = f" · necesar {qty}" if qty else ""
        lines.append(f"  - SKU {sku} (codmare {cm}){qty_str} {name}")
    if len(products) > 30:
        lines.append(f"  ... si inca {len(products) - 30} produse")
    return "\n".join(lines)


def _campaign_context(campaign: dict) -> str:
    return f"""Date campanie:

Nume: {campaign.get('name', '')}
Tip: {campaign.get('type', 'promo')}
Status: {campaign.get('status', 'draft')}
Mecanica: {campaign.get('mechanic') or '(nesetata)'}
Reducere: {_format_discount(campaign.get('discount'))}
Perioada: {campaign.get('date_start')} → {campaign.get('date_end')}
Canale: {', '.join(campaign.get('channels', [])) or '(nesetate)'}
Buget alocat: {campaign.get('budget_alloc') or 'nesetat'} RON

Produse incluse ({len(campaign.get('products', []))}):
{_format_products(campaign.get('products', []))}

Note utilizator: {campaign.get('notes') or '(fara)'}
"""


# JSON schema pentru output-ul structured
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "description_long": {
            "type": "string",
            "description": "Descriere lunga pentru blog/email/landing (150-300 cuvinte).",
        },
        "instagram_caption": {
            "type": "string",
            "description": "Caption pentru Instagram cu hashtag-uri RO (80-150 cuvinte).",
        },
        "facebook_caption": {
            "type": "string",
            "description": "Caption pentru Facebook, ton narativ (100-200 cuvinte).",
        },
        "hero_products": {
            "type": "array",
            "description": "2-4 produse de evidentiat ca star-ul campaniei.",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "De ce e ales (1-2 propozitii).",
                    },
                },
                "required": ["sku", "name", "reason"],
                "additionalProperties": False,
            },
        },
        "posting_plan": {
            "type": "array",
            "description": "3-5 momente cheie (teaser, lansare, reminder, ultima zi).",
            "items": {
                "type": "object",
                "properties": {
                    "phase": {"type": "string", "description": "ex: Teaser, Lansare, Reminder mid, Ultima zi"},
                    "when": {"type": "string", "description": "Data sau moment relativ (ex: cu 3 zile inainte)"},
                    "channel": {"type": "string", "description": "Instagram / Facebook / ambele"},
                    "summary": {"type": "string", "description": "Mesaj scurt (1-2 propozitii)"},
                },
                "required": ["phase", "when", "channel", "summary"],
                "additionalProperties": False,
            },
        },
        "warnings": {
            "type": "array",
            "description": "Avertismente pentru utilizator (stoc, mecanica, conflicte, etc).",
            "items": {"type": "string"},
        },
        "image_analysis": {
            "type": "string",
            "description": "Analiza pozei (daca e furnizata) si cum se foloseste; gol daca nu e poza.",
        },
    },
    "required": [
        "description_long",
        "instagram_caption",
        "facebook_caption",
        "hero_products",
        "posting_plan",
        "warnings",
        "image_analysis",
    ],
    "additionalProperties": False,
}


def generate_campaign_content(
    campaign: dict,
    image_bytes: bytes | None = None,
    image_media_type: str = "image/jpeg",
    extra_notes: str = "",
) -> dict:
    """Genereaza pachetul de continut marketing pentru o campanie.

    Args:
        campaign: dict cu datele campaniei (din storage)
        image_bytes: optional, bytes ai unei poze pentru analiza vizuala
        image_media_type: 'image/jpeg' / 'image/png' / 'image/webp' / 'image/gif'
        extra_notes: text suplimentar de la user

    Returns:
        dict cu cheile: ok, data, usage, error
    """
    client = get_client()
    if not client:
        return {
            "ok": False,
            "error": (
                "ANTHROPIC_API_KEY nu este setat in .env. "
                "Mergi la console.anthropic.com → API Keys → Create Key, "
                "copiaza key-ul si pune-l in fisierul .env din folder-ul proiectului. "
                "Apoi restarteaza serverul cu start.bat."
            ),
        }

    # Build user content (image + text)
    user_content: list[dict] = []
    if image_bytes:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type,
                "data": b64,
            },
        })

    text_block = _campaign_context(campaign)
    if extra_notes:
        text_block += f"\n\nIndicatii suplimentare de la utilizator:\n{extra_notes}\n"
    text_block += "\nGenereaza pachetul complet de continut, in JSON conform schemei."
    user_content.append({"type": "text", "text": text_block})

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=[
                # Cache breakpoint pe system prompt — stabil intre apeluri,
                # se cache-uieste si reduce costul la apelurile urmatoare cu ~90%
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key invalid sau expirat. Verifica .env."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limit atins pe API. Asteapta cateva secunde si reincearca."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Cerere invalida: {e}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Eroare API ({e.status_code}): {e.message}"}
    except Exception as e:
        log.exception("AI generation failed")
        return {"ok": False, "error": f"Eroare neasteptata: {e}"}

    # Extract JSON from text block in response
    parsed = None
    for block in response.content:
        if block.type == "text":
            try:
                parsed = json.loads(block.text)
                break
            except json.JSONDecodeError as e:
                log.error(f"Invalid JSON in AI response: {e}")
                continue

    if parsed is None:
        return {"ok": False, "error": "Raspunsul AI nu contine JSON valid."}

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
        "stop_reason": response.stop_reason,
    }
