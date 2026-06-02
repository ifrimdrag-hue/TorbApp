"""Generator AI pentru postari Instagram + Facebook.

Diferenta fata de campaign content generator:
  - Focus pe poza (input principal — analizam ce e in ea)
  - Output specific platformei (IG vs FB au stiluri diferite)
  - Optional: leagatura cu o campanie activa (mosteneste mecanica/produse)
  - Mai scurt si mai 'feed-ready' decat continutul de campanie
"""

import base64
import json
import logging

import anthropic

from config import settings
from .claude_client import get_client


log = logging.getLogger(__name__)


SYSTEM_PROMPT_POSTS = """Esti specialist in social media pentru o afacere e-commerce romaneasca \
care vinde:
- Ceaiuri premium: Basilur, Kingsleaf, Tipson
- Ciocolata fara zahar/gluten: Torras, Delaviuda, El Almendro
- Marca proprie ceai: Celmar
- Produse din bumbac: Leonex
- Vopsea de par: Miss Magic Creative

Sarcina ta: pe baza unei poze furnizate, generezi o postare pentru Instagram SAU Facebook \
(platforma e specificata in cerere). NU le faci pe amandoua — doar pe cea ceruta.

Diferentele intre platforme:

INSTAGRAM:
- Caption: 80-150 cuvinte, 3-5 paragrafe scurte cu line break-uri
- Stil: vizual-prim, evocativ, senzorial (descrie textura, aroma, culoarea)
- Emoji: moderat-spre-bogat (4-8)
- Hashtag-uri: 8-12 la final, mix de romanesti si internationale, in bloc separat
- Call to action: discret, "link in bio", "save pentru mai tarziu", "tag un prieten"

FACEBOOK:
- Caption: 100-200 cuvinte, mai narativ, ca o mini-poveste
- Stil: conversational, "noi" inclusiv (build community), invita la comentarii
- Emoji: putini (1-3), bine plasati
- Hashtag-uri: 2-4 maxim, integrate in text sau la final ca optiune
- Call to action: clar, "comenteaza...", "tag pe cineva care...", "vezi in store"

Reguli generale:
1. Limba: romana corecta, fara diacritice obligatorii (autocompletul utilizatorului le va adauga)
2. Daca poza arata un produs specific dintr-un brand cunoscut, mentioneaza-l natural
3. Fara cliseuri AI ("descopera magia...", "calatoria gustativa...", etc)
4. Daca user-ul leaga postarea de o campanie activa, integreaza mecanica reducerii natural \
   (nu o forta, nu o repeta de mai multe ori)
5. Hashtag-urile sa fie relevante: amesteca brand + categorie + lifestyle + romanesti

Output: JSON valid conform schemei.
"""


OUTPUT_SCHEMA_POSTS = {
    "type": "object",
    "properties": {
        "image_analysis": {
            "type": "string",
            "description": "Ce vezi in poza (compozitie, produse, mood, culori). 2-4 propozitii.",
        },
        "caption": {
            "type": "string",
            "description": "Caption-ul final pentru platforma (cu line break-uri si emoji daca e cazul).",
        },
        "hashtags": {
            "type": "array",
            "description": "Lista de hashtag-uri relevante (cu # inclus).",
            "items": {"type": "string"},
        },
        "alt_text": {
            "type": "string",
            "description": "Text alternativ pentru accesibilitate (descriere obiectiva a pozei).",
        },
        "posting_tips": {
            "type": "array",
            "description": "1-3 tip-uri concrete despre cand/cum sa postezi (timing, story-uri, etc).",
            "items": {"type": "string"},
        },
        "warnings": {
            "type": "array",
            "description": "Avertismente (poza necalitativa, conflict cu brandul, ton greset, etc).",
            "items": {"type": "string"},
        },
    },
    "required": ["image_analysis", "caption", "hashtags", "alt_text", "posting_tips", "warnings"],
    "additionalProperties": False,
}


PLATFORM_LABELS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
}

TONE_DESCRIPTIONS = {
    "casual": "Casual, prietenesc, conversational. Ca si cum ai vorbi cu un prieten.",
    "promo": "Promotional, orientat catre vanzare. Subliniaza beneficii, oferte, urgenta.",
    "lifestyle": "Lifestyle, aspirational. Pune produsul intr-un context de viata frumoasa.",
    "educational": "Educational, informativ. Explica beneficii, originea produsului, cum se foloseste.",
    "storytelling": "Povestire. Construieste o mini-naratiune in jurul produsului.",
}


def _format_linked_campaign(campaign: dict | None) -> str:
    if not campaign:
        return "(postarea nu e legata de o campanie — postare independenta)"
    d = campaign.get("discount") or {}
    discount_str = ""
    if d.get("type") == "percent_off":
        discount_str = f" cu reducere -{d.get('value')}%"
    elif d.get("type") == "fixed_off":
        discount_str = f" cu reducere -{d.get('value')} RON"
    elif d.get("type") == "fixed_price":
        discount_str = f" la pret special de {d.get('value')} RON"
    return f"""Postarea face parte din campania activa:
- Nume: {campaign.get('name')}
- Tip: {campaign.get('type')}
- Mecanica: {campaign.get('mechanic') or '(nesetata)'}{discount_str}
- Perioada: {campaign.get('date_start')} → {campaign.get('date_end')}

Integreaza mecanica natural in caption — fara sa o repeti, fara sa fie pushy.
"""


def generate_post_content(
    image_bytes: bytes,
    image_media_type: str,
    platform: str,
    brand: str | None = None,
    tone: str | None = None,
    notes: str = "",
    linked_campaign: dict | None = None,
) -> dict:
    """Genereaza continut pentru o postare Instagram sau Facebook."""
    client = get_client()
    if not client:
        return {
            "ok": False,
            "error": (
                "ANTHROPIC_API_KEY nu este setat in .env. "
                "Mergi la console.anthropic.com → API Keys → Create Key, "
                "lipeste key-ul in .env si restarteaza serverul."
            ),
        }

    if platform not in PLATFORM_LABELS:
        return {"ok": False, "error": f"Platforma necunoscuta: {platform}. Foloseste 'instagram' sau 'facebook'."}

    if not image_bytes:
        return {"ok": False, "error": "Trebuie o poza pentru generare."}

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    # Build user content
    user_text_parts = [
        f"Platforma tinta: **{PLATFORM_LABELS[platform]}**",
    ]
    if brand:
        user_text_parts.append(f"Brand-ul produsului: {brand}")
    if tone:
        tone_desc = TONE_DESCRIPTIONS.get(tone, tone)
        user_text_parts.append(f"Ton dorit: {tone} — {tone_desc}")
    user_text_parts.append("")
    user_text_parts.append(_format_linked_campaign(linked_campaign))
    if notes:
        user_text_parts.append(f"\nIndicatii suplimentare: {notes}")
    user_text_parts.append(f"\nGenereaza pachetul complet pentru postarea pe {PLATFORM_LABELS[platform]} pe baza pozei furnizate.")

    user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": image_media_type, "data": b64},
        },
        {
            "type": "text",
            "text": "\n".join(user_text_parts),
        },
    ]

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA_POSTS},
            },
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT_POSTS,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "API key invalid. Verifica .env."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limit. Asteapta cateva secunde si reincearca."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Cerere invalida: {e}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Eroare API ({e.status_code}): {e.message}"}
    except Exception as e:
        log.exception("post AI generation failed")
        return {"ok": False, "error": f"Eroare neasteptata: {e}"}

    parsed = None
    for block in response.content:
        if block.type == "text":
            try:
                parsed = json.loads(block.text)
                break
            except json.JSONDecodeError:
                continue

    if parsed is None:
        return {"ok": False, "error": "Raspunsul AI nu contine JSON valid."}

    return {
        "ok": True,
        "platform": platform,
        "data": parsed,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "model": response.model,
        },
    }
