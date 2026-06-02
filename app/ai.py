"""
AI query module — uses the Anthropic Python SDK.

Call flow:
  ask_question(question) → claude-sonnet (SQL) → execute → claude-haiku (answer)
"""

import json
import logging
import os
import re

import anthropic
from db import query

logger = logging.getLogger(__name__)

# On Windows, Python may not use the OS cert store by default — inject it.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ''))
    return _client

# ---------------------------------------------------------------------------
# Schema / system prompts
# ---------------------------------------------------------------------------

_SCHEMA = """You are a SQL expert for Torb Logistic SRL, a Romanian FMCG distribution company.

DATABASE: torb.db (SQLite) — ~137,000 rows, data range 2024-01-03 → 2026-04-29

TABLE tranzactii (one row = one SKU line on one delivery/invoice):
  id, luna (month 1-12), an (year), data_dl (date ISO)
  nr_dl, nr_factura, nr_comanda
  cod_produs, sku, furnizor (= BRAND name, NOT the Sri Lanka vendor)
  um, cantitate, pret_vanzare, pret_cumparare
  val_neta   ← PRIMARY revenue metric
  val_achizitie, marja_bruta (= val_neta - val_achizitie)
  discount_pct, discount_val
  client, cod_client, tip_client (IKA/TT/Pharma/Online/Distribuitor/HoReCa)
  oras_client, judet_client
  agent  ← human: DRAGNEA BOGDAN, Oana Filip, BRINZA CLAUDIU,
                   BOTEA DANIEL, CONSTANTIN IONUT, GURAMULTA GHEORGHE,
                   REICH LEOPOLD
           digital: EMAG, SITE, TRENDYOL, ALTEX
  Note: agent names case is mixed — use exactly as stored. "Oana Filip"
        is Title Case (NOT "OANA FILIP"). For safe filtering use COLLATE NOCASE
        or LOWER(agent) = LOWER('...').

VIEWS:
  v_vanzari_an_furnizor(an, furnizor, val_neta, marja_bruta, marja_pct, nr_clienti, nr_sku)
  v_vanzari_luna_agent(an, luna, agent, val_neta, marja_bruta, marja_pct)
  v_vanzari_luna_furnizor(an, luna, furnizor, val_neta, marja_bruta, marja_pct, cantitate)
  v_top_sku(an, furnizor, cod_produs, sku, val_neta, marja_bruta, cantitate, nr_clienti)
  v_clienti(client, cod_client, tip_client, ..., ultima_comanda, val_neta_total, agent_principal)

GLOSSARY:
  furnizor = brand (Basilur, Toras, Leonex, Celmar, etc.) — NOT the external supplier
  val_neta = net revenue — always use this as the revenue figure
  marja_bruta = gross margin RON
  IKA = modern trade (Kaufland, Carrefour, Mega Image, Auchan, Selgros, Metro)
  TT = traditional trade
  YTD = year-to-date (filter: data_dl <= date('now'))
  Kaufland is stored as "KAUFLAND ROMANIA SCS" — use LIKE '%KAUFLAND%'
  julianday('now') for elapsed-days calculations
"""

_SQL_INSTRUCTIONS = (
    "Generate a single SQLite-compatible SELECT query to answer the user's question.\n"
    "Return ONLY valid JSON — no markdown, no code fences, nothing else:\n"
    '{"sql": "SELECT ...", "explanation": "Brief explanation in Romanian"}\n\n'
    "Rules:\n"
    "- Only SELECT — never INSERT, UPDATE, DELETE, DROP, CREATE.\n"
    "- Use NULLIF() to avoid division by zero.\n"
    "- Use ROUND() for money (2 dec) and percentages (1 dec).\n"
    "- Default LIMIT 100 rows unless the question needs all data.\n"
    "- Q1=luna IN(1,2,3), Q2=(4,5,6), Q3=(7,8,9), Q4=(10,11,12).\n"
)

_ANSWER_SYSTEM = (
    "Ești analist de business pentru o firmă română de distribuție FMCG. "
    "Formulează un răspuns concis și clar în română pe baza rezultatelor SQL. "
    "Folosește RON pentru valori monetare. Fii direct și factual. "
    "Maximum 3 propoziții. Nu repeta întrebarea. Nu explica SQL-ul."
)


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str):
    """Try several strategies to pull a JSON object out of raw LLM output."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    clean = text
    if '```' in clean:
        for block in clean.split('```'):
            s = block.lstrip('json').strip()
            if s.startswith('{'):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
    m = re.search(r'\{[^{}]*"sql"[^{}]*\}', clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _call_anthropic(system: str, user: str, model: str) -> str:
    msg = _get_client().messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{'role': 'user', 'content': user}],
    )
    return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask_question(question: str) -> dict:
    """
    Convert a natural-language question to SQL, execute it, return a Romanian answer.
    Returns dict with keys: answer, sql, rows, explanation  (or error on failure).
    """
    # --- Step 1: generate SQL ---
    try:
        raw = _call_anthropic(
            system=_SCHEMA + '\n\n' + _SQL_INSTRUCTIONS,
            user=f'Question: {question}',
            model='claude-haiku-4-5-20251001',
        )
    except Exception as exc:
        logger.exception("Anthropic SQL call failed for question: %s", question[:120])
        return {'error': f'Eroare la apelul AI: {exc}', 'sql': '', 'rows': []}

    parsed = _extract_json(raw)
    if not parsed:
        return {'error': 'Nu am putut extrage SQL din răspuns.', 'sql': raw, 'rows': []}

    sql = parsed.get('sql', '').strip()
    explanation = parsed.get('explanation', '')

    if not sql.lstrip(';').strip().upper().startswith('SELECT'):
        return {
            'error': 'Interogare respinsă — sunt permise doar instrucțiuni SELECT.',
            'sql': sql, 'rows': [],
        }

    # --- Step 2: execute ---
    try:
        rows = query(sql)
    except Exception as exc:
        logger.exception("SQL execution failed: %s", sql[:200])
        return {'error': f'Eroare la execuția SQL: {exc}', 'sql': sql, 'rows': []}

    if not rows:
        return {
            'answer': 'Nu s-au găsit rezultate pentru această interogare.',
            'sql': sql, 'rows': [], 'explanation': explanation,
        }

    # --- Step 3: format answer ---
    try:
        answer = _call_anthropic(
            system=_ANSWER_SYSTEM,
            user=(
                f'Întrebare: {question}\n\n'
                f'Rezultate SQL (primele 20 rânduri):\n'
                f'{json.dumps(rows[:20], ensure_ascii=False)}'
            ),
            model='claude-haiku-4-5-20251001',
        )
    except Exception as exc:
        logger.warning("Anthropic answer formatting failed: %s", exc)
        answer = f'(Eroare la formatarea răspunsului: {exc})'

    return {
        'answer': answer,
        'sql': sql,
        'rows': rows[:100],
        'explanation': explanation,
    }
