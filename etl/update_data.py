"""
Pipeline master de actualizare date Torb.

Detectează automat cel mai recent folder datat din docs_input/ (DD.MM.YYYY),
importă vânzările și stocul, și actualizează coloana gama în produse.

Usage:
    python update_data.py
    python update_data.py --folder 24.04.2026   # folder specific
"""

import sys
import os
import re
from datetime import date

# Windows UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Allow importing sibling ETL modules (rebuild_db, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = "data/torb.db"
DOCS_PATH = "docs_input"

# Mapping furnizor → gama
GAMA_MAP = {
    "Basilur":   "Basilur",
    "Organsia":  "Organsia",
    "Celmar":    "Celmar",
    "KingsLeaf": "KingsLeaf",
    "Toras":     "Toras",
    "Leonex":    "Leonex",
    "Tipson":    "Tipson",
    "Delaviuda": "Delaviuda",
    "Colian":    "Colian",
    "Cosmetice": "Cosmetice",
    "Solvex":    "Solvex",
    "Foite":     "Foite",
    "Altele":    "Altele",
}


def find_latest_folder():
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    candidates = []
    for entry in os.listdir(DOCS_PATH):
        if date_pattern.match(entry) and os.path.isdir(os.path.join(DOCS_PATH, entry)):
            day, month, year = entry.split(".")
            candidates.append((date(int(year), int(month), int(day)), entry))
    if not candidates:
        return None, None
    candidates.sort(reverse=True)
    folder_date, folder_name = candidates[0]
    return folder_date, os.path.join(DOCS_PATH, folder_name)


def find_file(folder, prefix, extensions):
    for f in os.listdir(folder):
        name_lower = f.lower()
        if name_lower.startswith(prefix.lower()):
            for ext in extensions:
                if name_lower.endswith(ext):
                    return os.path.join(folder, f)
    return None


def ensure_gama_column(conn):
    """Add gama column to produse if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(produse)")
    cols = [r[1] for r in cursor.fetchall()]
    if "gama" not in cols:
        conn.execute("ALTER TABLE produse ADD COLUMN gama TEXT")
        conn.commit()
        print("  → Coloana 'gama' adăugată în tabelul produse.")


def assign_gama(conn):
    """Populate gama in produse based on furnizor."""
    cursor = conn.cursor()

    # Update gama for known furnizori
    updated = 0
    for furnizor, gama in GAMA_MAP.items():
        cursor.execute(
            "UPDATE produse SET gama=? WHERE furnizor=? AND (gama IS NULL OR gama != ?)",
            (gama, furnizor, gama),
        )
        updated += cursor.rowcount

    # Fallback: use furnizor as gama where gama is still null
    cursor.execute(
        "UPDATE produse SET gama=furnizor WHERE gama IS NULL AND furnizor IS NOT NULL"
    )
    updated += cursor.rowcount

    conn.commit()

    # Report
    cursor.execute("SELECT gama, COUNT(*) as n FROM produse GROUP BY gama ORDER BY n DESC")
    rows = cursor.fetchall()
    print(f"  → Gama asignată: {updated} produse actualizate")
    for gama, n in rows:
        print(f"     {gama or '(null)':15s}: {n:4d} SKU-uri")


def assign_gama_tranzactii(conn):
    """
    Also update gama on stoc table based on the gama assignment logic.
    (tranzactii doesn't have a gama column — use produse JOIN at query time)
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(stoc)")
    cols = [r[1] for r in cursor.fetchall()]
    if "gama" not in cols:
        return

    # Update stoc.gama from GAMA_MAP via furnizor
    for furnizor, gama in GAMA_MAP.items():
        cursor.execute(
            "UPDATE stoc SET gama=? WHERE furnizor=? AND (gama IS NULL OR gama != ?)",
            (gama, furnizor, gama),
        )
    conn.commit()


def main():
    # Detecteaza fisierul de vanzari: argument --vanzari, folder datat, sau rapoarte/
    vanzari_file = None
    if "--vanzari" in sys.argv:
        idx_v = sys.argv.index("--vanzari")
        if idx_v + 1 < len(sys.argv):
            vanzari_file = sys.argv[idx_v + 1]
    elif "--folder" in sys.argv:
        idx_f = sys.argv.index("--folder")
        if idx_f + 1 < len(sys.argv):
            folder_path = os.path.join(DOCS_PATH, sys.argv[idx_f + 1])
            vanzari_file = find_file(folder_path, "vanzari", [".xlsx", ".xls"])
    else:
        _, folder_path = find_latest_folder()
        if folder_path:
            vanzari_file = find_file(folder_path, "vanzari", [".xlsx", ".xls"])
        if not vanzari_file:
            rapoarte = os.path.join(DOCS_PATH, "rapoarte")
            if os.path.isdir(rapoarte):
                vanzari_file = find_file(rapoarte, "vanzari", [".xlsx", ".xls"])

    # Rebuild complet: sterge DB vechi, reimporta totul din sursa curenta
    import rebuild_db
    rebuild_db.main(vanzari_file=vanzari_file)


if __name__ == "__main__":
    main()
