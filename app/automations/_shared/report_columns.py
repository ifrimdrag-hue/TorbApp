"""Configurare coloane raport intern (raport-stoc-DD-MM-YYYY.xls).

Numele se compara case-insensitive si fara spatii la capete.
Coloanele suplimentare din raport sunt ignorate complet.
"""

# Cod intern produs (SKU principal pentru deduplicare)
COLUMN_SKU = "cod"

# Cod alternativ — pentru Basilur/Kingsleaf/Tipson are formatul "71395-00" si se
# potriveste cu Variant SKU pe Shopify. Pentru alte produse e cod 3-cifre simplu
# care nu apare pe Shopify (vor fi ignorate la sincronizarea Shopify).
COLUMN_CODMARE = "codmare"

# Cod EAN / cod de bare — pentru match cu eMAG
COLUMN_EAN = "codbare"

# Cantitate (se sumeaza intre randuri cu acelasi SKU — diferite loturi)
COLUMN_QTY = "cantit"
