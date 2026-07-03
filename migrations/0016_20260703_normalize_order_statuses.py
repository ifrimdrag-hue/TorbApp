"""
Migration 0016 -- normalize_order_statuses.

Legacy tranzit-import ETLs once wrote capitalized supplier-order statuses
('Emisa', 'Confirmata', 'In tranzit'); the UI, agent, and current ETLs all use
the lowercase vocabulary (draft/confirmata/in_tranzit/livrata/anulata). The two
spellings never matched in the status dropdown, so editing a legacy order could
write status='' and drop it from every in-transit calculation (finding A2).

This one-time migration folds the capitalized values into the canonical
lowercase set so every order is UI-editable and counted consistently.
'Emisa' (sent, not yet confirmed) maps to the closest UI-representable state
that still counts as incoming stock: 'confirmata'. Idempotent.
"""

VERSION = 16
NAME = "0016_20260703_normalize_order_statuses"

MAPPING = [
    ("Emisa", "confirmata"),
    ("Confirmata", "confirmata"),
    ("In tranzit", "in_tranzit"),
    ("Receptionata", "livrata"),
]


def up(conn):
    for old, new in MAPPING:
        conn.execute(
            "UPDATE comenzi_furnizori SET status = ? WHERE status = ?",
            (new, old),
        )
