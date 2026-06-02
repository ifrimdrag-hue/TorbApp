"""
Forecast AI Agent — specialized for Torb Logistic procurement decisions.
"""
import json
import logging
from db import query
from ai import _call_claude

logger = logging.getLogger(__name__)

_SYSTEM = """Ești un agent de procurement specializat pentru Torb Logistic SRL, un distribuitor FMCG din România.

CONTEXT BUSINESS:
- Torb distribuie ~15M RON/an, 3.297 clienți, 12 branduri principale
- Branduri principale: Basilur 31%, Toras 22%, Leonex 20%, Celmar 13%
- Client major: Kaufland — 41.4% din revenue (risc concentrare ridicat)
- Agent principal: Bogdan Dragnea — 55.6% din vânzări

TERMENE DE APROVIZIONARE:
- Basilur, Kings Leaf, Tipson: 4 luni (120 zile) — import extraeuropean
- Toras: 1,5 luni (45 zile)
- Delaviuda, Celmar, Leonex: 1 lună (30 zile)

SEZONALITATE IMPORTANTĂ:
- Produse Crăciun (Basilur, Kings Leaf, Tipson): vârf de vânzări Oct-Nov
- Fereastra de comandă Crăciun: APRILIE-MAI → livrare August → vânzări Oct-Nov
- Produsele trebuie comandate ACUM (apr-mai) dacă dorești stoc la Crăciun

REGULI DE APROVIZIONARE:
1. Stoc de siguranță recomandat: 30 zile peste termenul de livrare
2. Comenzile confirmate/în tranzit se consideră stoc disponibil (scad necesarul)
3. Listări noi la clienți cresc necesarul; delistările îl scad
4. Prețurile furnizorilor sunt în EUR sau GBP — cursul mediu BNR

PROCESUL DE COMANDĂ:
Draft → Confirmată → În Tranzit → Livrată (sau Anulată)

Răspunde CONCIS în română. Fii specific cu cantități și date.
Când dai sugestii de aprovizionare, explică raționamentul:
sezonalitate, stoc curent, termen livrare, comenzi existente în tranzit.
"""


def _build_context(furnizor: str = None) -> str:
    parts = []

    if furnizor:
        # Current stock for brand
        stock = query("""
            SELECT sku, SUM(cantitate) AS qty,
                   ROUND(SUM(cantitate * pret_achizitie), 0) AS val
            FROM stoc
            WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
              AND furnizor = :f AND cantitate > 0
            GROUP BY sku ORDER BY qty DESC LIMIT 20
        """, {'f': furnizor})
        if stock:
            parts.append(f"STOC CURENT {furnizor.upper()} (top 20 SKU):\n"
                         + json.dumps(stock, ensure_ascii=False))

        # In-transit for brand
        transit = query("""
            SELECT l.sku, COALESCE(l.cantitate_confirmata, l.cantitate_comandata) AS qty,
                   c.data_estimata_livrare, c.nr_comanda, c.status
            FROM comenzi_furnizori_linii l
            JOIN comenzi_furnizori c ON c.id = l.comanda_id
            WHERE c.furnizor = :f AND c.status IN ('confirmata', 'in_tranzit')
        """, {'f': furnizor})
        if transit:
            parts.append(f"COMENZI ÎN TRANZIT {furnizor.upper()}:\n"
                         + json.dumps(transit, ensure_ascii=False))

        # Recent 3-month sales velocity for brand
        velocity = query("""
            SELECT sku, ROUND(SUM(cantitate) / 3.0, 1) AS avg_luna
            FROM tranzactii
            WHERE furnizor = :f AND data_dl >= date('now', '-90 days')
            GROUP BY sku ORDER BY avg_luna DESC LIMIT 20
        """, {'f': furnizor})
        if velocity:
            parts.append(f"VITEZĂ VÂNZĂRI {furnizor.upper()} (avg/lună, ult. 3 luni):\n"
                         + json.dumps(velocity, ensure_ascii=False))

    # All active orders summary
    active = query("""
        SELECT c.furnizor, c.nr_comanda, c.status, c.data_comanda,
               c.data_estimata_livrare, COUNT(l.id) AS nr_linii,
               SUM(COALESCE(l.cantitate_confirmata, l.cantitate_comandata)) AS total_qty
        FROM comenzi_furnizori c
        LEFT JOIN comenzi_furnizori_linii l ON l.comanda_id = c.id
        WHERE c.status NOT IN ('livrata', 'anulata')
        GROUP BY c.id ORDER BY c.data_comanda DESC LIMIT 15
    """)
    if active:
        parts.append("COMENZI ACTIVE (toate brandurile):\n"
                     + json.dumps(active, ensure_ascii=False))

    return '\n\n'.join(parts)


def forecast_ask(question: str, furnizor: str = None) -> dict:
    context = _build_context(furnizor)
    user_msg = question
    if context:
        user_msg = f"Date curente din sistem:\n{context}\n\nÎntrebare: {question}"
    try:
        answer = _call_claude(system=_SYSTEM, user=user_msg, model='sonnet', timeout=90)
        return {'answer': answer}
    except Exception as exc:
        logger.exception("forecast_ask failed for question: %s", question[:120])
        return {'error': str(exc)}
