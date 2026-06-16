"""
Backfill obiective bonus pentru lunile deja consumate (ian–iun 2026).

Sistemul vechi de bonus calcula obiectivele „din zbor" din PRESETS (PY same-month
+20%, ponderi vânzări/marjă/strategic). Noul sistem citește obiectivele salvate în
`bonus_lunar_config` + `bonus_obiective_strategice`. Acest script reconstruiește
fidel obiectivele istorice ca rânduri KPI individuale, ca tracker-ul să afișeze
lunile trecute populate (nu goale).

Reguli reproduse din modelul vechi:
  - target vânzări  = SUM(val_neta) anul trecut aceeași lună * (1 + growth)
  - target marjă    = SUM(marja_bruta) anul trecut aceeași lună * (1 + growth)
  - 5 game strategice: target = val_neta gamă PY same-month * (1 + growth),
    pondere = w_strategic * greutatea_brandului (Basilur .30, Toras .25, Leonex .20,
    Celmar .15, Delaviuda .10) — astfel suma ponderilor = w_sales+w_margin+w_strategic.
  - monthly_bonus  = valoarea din seed-ul 2025 (Claudiu/Bogdan 4000, Oana 3000, Ionut 2000).

Idempotent: sare peste (an, lună, agent) care au deja obiective salvate.

Rulează din rădăcina proiectului:
    python etl/backfill_bonus_obiective.py            # 2026, lunile 1-6 (implicit)
    python etl/backfill_bonus_obiective.py --an 2026 --luni 1-6 --dry-run
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

import queries  # noqa: E402
from db import query  # noqa: E402

# Greutățile brandurilor strategice în interiorul componentei „strategic"
# (reproduse din vechiul STRATEGIC_WEIGHTS_DEFAULT; sumă = 1.0).
STRATEGIC_WEIGHTS = {
    "Basilur": 0.30,
    "Toras": 0.25,
    "Leonex": 0.20,
    "Celmar": 0.15,
    "Delaviuda": 0.10,
}


def _monthly_bonus(agent_key):
    """Valoarea bonusului lunar din seed-ul 2025 (fallback 0 dacă lipsește)."""
    rows = query(
        "SELECT monthly_bonus FROM bonus_lunar_config "
        "WHERE agent_key=:k AND an=2025 ORDER BY luna LIMIT 1",
        {"k": agent_key},
    )
    return rows[0]["monthly_bonus"] if rows else 0.0


def _build_kpis(cfg, db_agent, an, luna):
    """Construiește rândurile KPI reproducând obiectivele vechi (PY +20%)."""
    growth = cfg.get("growth_pct") or 0.20
    g = 1.0 + growth
    py = queries.py_baseline(db_agent, an, luna)

    w_sales = cfg.get("w_sales") or 0.0
    w_margin = cfg.get("w_margin") or 0.0
    w_strategic = cfg.get("w_strategic") or 0.0

    kpis = [
        {"tip": "vanzari", "referinta": None,
         "target": round(py["vanzari"] * g), "unitate": "ron", "pondere": round(w_sales, 4)},
        {"tip": "marja", "referinta": None,
         "target": round(py["marja"] * g), "unitate": "ron", "pondere": round(w_margin, 4)},
    ]
    for brand, bw in STRATEGIC_WEIGHTS.items():
        base = py["brand"].get(brand, 0) or 0
        kpis.append({
            "tip": "brand", "referinta": brand,
            "target": round(base * g), "unitate": "ron",
            "pondere": round(w_strategic * bw, 4),
        })
    return kpis


def _parse_luni(spec):
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def main():
    ap = argparse.ArgumentParser(description="Backfill obiective bonus istorice")
    ap.add_argument("--an", type=int, default=2026)
    ap.add_argument("--luni", default="1-6", help="ex: 1-6 sau 1,2,3")
    ap.add_argument("--dry-run", action="store_true", help="afișează fără a scrie")
    args = ap.parse_args()

    luni = _parse_luni(args.luni)
    # Doar agenții de teren (au db_agent cu un singur agent, fără '|').
    agents = [a for a in queries.bonus_agents(activ_only=True)
              if a["db_agent"] and "|" not in a["db_agent"]]

    print(f"Backfill an={args.an} luni={luni} agenți={[a['agent_key'] for a in agents]}"
          f"{' (DRY-RUN)' if args.dry_run else ''}\n")

    for a in agents:
        # bonus_agents nu întoarce ponderile — le luăm din bonus_config complet.
        cfg = dict(query(
            "SELECT w_sales, w_margin, w_strategic, growth_pct FROM bonus_config "
            "WHERE agent_key=:k", {"k": a["agent_key"]})[0])
        mb = _monthly_bonus(a["agent_key"])

        for luna in luni:
            existing = queries.obiective(args.an, luna, a["agent_key"])
            if existing:
                print(f"  [skip] {a['agent_key']:<8} {args.an}-{luna:02d}: "
                      f"{len(existing)} obiective deja există")
                continue
            kpis = _build_kpis(cfg, a["db_agent"], args.an, luna)
            total_pond = round(sum(k["pondere"] for k in kpis) * 100)
            if args.dry_run:
                print(f"  [dry ] {a['agent_key']:<8} {args.an}-{luna:02d}: "
                      f"bonus={mb:.0f} pond={total_pond}% "
                      f"vânz_target={kpis[0]['target']:,} ({len(kpis)} KPI)")
            else:
                queries.save_obiective(args.an, luna, a["agent_key"],
                                       mb, cfg.get("growth_pct") or 0.20, kpis)
                print(f"  [ok  ] {a['agent_key']:<8} {args.an}-{luna:02d}: "
                      f"bonus={mb:.0f} pond={total_pond}% "
                      f"vânz_target={kpis[0]['target']:,} ({len(kpis)} KPI)")

    print("\nGata.")


if __name__ == "__main__":
    main()
