"""Generator AI pentru postari automate (cross-post IG + FB cu acelasi caption).

Diferente fata de post_generator clasic:
- Detecteaza brand-ul automat din poza (vision)
- Genereaza UN caption care merge bine pe IG si FB
- Genereaza 15-25 hashtag-uri cu mix de trending + nisa + brand
- Suporta regenerare cu feedback de la user ("mai scurt", "fara emoji", etc)
"""

import base64
import json
import logging

import anthropic

from config import settings
from automations.ai.claude_client import get_client


log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Esti specialist senior in social media pentru o afacere e-commerce \
romaneasca care vinde produse premium:
- Ceaiuri: Basilur (Sri Lanka, premium pachete colectie), Kingsleaf, Tipson, Organsia, Celmar (marca proprie)
- Ciocolata fara zahar/gluten: Torras, Delaviuda, El Almendro
- Bumbac: Leonex
- Vopsea de par: Miss Magic Creative

Sarcina: pe baza unei poze, generezi UN PACHET de continut cross-post care merge \
identic pe Instagram SI Facebook. Acelasi caption va fi postat manual pe ambele.

Reguli pentru caption:
- 90-160 cuvinte, 3-5 paragrafe scurte cu line break-uri
- Mix intre stilul vizual-evocativ (IG) si conversational (FB)
- Limba: romana corecta gramatical, FARA diacritice obligatorii
- Emoji moderat: 3-6 in tot caption-ul, plasati natural
- 1 call-to-action discret la final ("comenteaza", "tag prieten", "salveaza pentru mai tarziu", "link in bio")
- FARA cliseuri AI ("descopera magia", "calatorie senzoriala", "experienta unica", etc)
- Daca poza arata clar un produs cu brand recognizabil, mentioneaza-l natural in caption

Reguli pentru hashtag-uri (CRITIC pentru reach):
- Total 18-22 hashtag-uri
- Strategie mix:
  * 3-5 hashtag-uri brand specifice (#basilur, #kingsleaf, #celmar, etc — daca recunosti brandul)
  * 5-7 hashtag-uri categorie/produs (#ceaipremium, #ceaiulibere, #ciocolatafarazahar, #icetea)
  * 6-8 hashtag-uri TRENDING / high-volume RO+EN (lifestyle, mood) — cele care apar in tendinte:
    #foryou #fyp #explorepage #romania #lifestyle #aesthetic #cozy #morningvibes #weekendmood \
    #selfcare #mindfulliving #slowliving #hygge — alege 6-8 RELEVANTE pentru poza
  * 2-3 hashtag-uri nisa/comunitate RO (#tealoversromania, #ceaiuripremium, #romaniandelights)
- Fara hashtag-uri spam (#like4like, #followforfollow), fara hashtag-uri banate
- Toate cu # inclus, fara spatii

Brand detection: uita-te atent la logo-uri, ambalaje, texte vizibile pe produs. Daca nu \
recunosti brand specific, lasa "brand_detected" = null si genereaza captionul mai general.

Output: JSON valid conform schemei.
"""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_analysis": {
            "type": "string",
            "description": "Ce vezi in poza (compozitie, produse, mood, culori). 2-4 propozitii.",
        },
        "brand_detected": {
            "type": ["string", "null"],
            "description": "Brand-ul detectat din poza (ex: Basilur, Kingsleaf, Torras) sau null.",
        },
        "caption": {
            "type": "string",
            "description": "Caption final pentru cross-post IG+FB (cu line break-uri si emoji).",
        },
        "hashtags": {
            "type": "array",
            "description": "18-22 hashtag-uri cu # inclus, mix brand + categorie + trending + nisa.",
            "items": {"type": "string"},
        },
        "alt_text": {
            "type": "string",
            "description": "Text alternativ pentru accesibilitate (descriere obiectiva).",
        },
        "warnings": {
            "type": "array",
            "description": "Avertismente: poza necalitativa, conflict brand, etc. Lista poate fi goala.",
            "items": {"type": "string"},
        },
    },
    "required": ["image_analysis", "brand_detected", "caption", "hashtags", "alt_text", "warnings"],
    "additionalProperties": False,
}


def generate_auto_post(
    image_bytes: bytes,
    image_media_type: str,
    regen_feedback: str = "",
    previous_caption: str = "",
) -> dict:
    """Genereaza pachetul pentru o postare cross-post (IG+FB)."""
    client = get_client()
    if not client:
        return {
            "ok": False,
            "error": (
                "ANTHROPIC_API_KEY nu este setat in .env. "
                "Adauga key-ul in fisierul .env si restarteaza serverul."
            ),
        }

    if not image_bytes:
        return {"ok": False, "error": "Lipseste poza."}

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    user_text = "Genereaza pachetul de continut pentru aceasta poza."
    if regen_feedback or previous_caption:
        parts = ["REGENERARE solicitata."]
        if previous_caption:
            parts.append(f"\nCaption anterior (NU il repeta — fa altceva):\n{previous_caption[:500]}")
        if regen_feedback:
            parts.append(f"\nIndicatii de la user: {regen_feedback}")
        parts.append("\nGenereaza o varianta NOUA care raspunde indicatiilor.")
        user_text = "\n".join(parts)

    user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": image_media_type, "data": b64},
        },
        {"type": "text", "text": user_text},
    ]

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
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
        log.exception("auto-post AI generation failed")
        return {"ok": False, "error": f"Eroare neasteptata: {e}"}

    parsed = None
    for block in response.content:
        if block.type == "text":
            try:
                parsed = json.loads(block.text)
                break
            except json.JSONDecodeError as e:
                log.error("Invalid JSON in auto-post AI response: %s — %.200s", e, block.text)
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
    }
