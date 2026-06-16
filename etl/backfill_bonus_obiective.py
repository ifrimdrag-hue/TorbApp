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

# Valori canonice ale bonusului lunar (din PRESETS-ul original) — folosite când
# seed-ul 2025 lipsește (ex. pe producție), ca să nu rezulte monthly_bonus=0.
DEFAULT_BONUS = {"Claudiu": 4000.0, "Bogdan": 4000.0, "Oana": 3000.0, "Ionut": 2000.0}


def _monthly_bonus(agent_key):
    """Bonus lunar: seed-ul 2025 (dacă >0), altfel valoarea canonică implicită."""
    rows = query(
        "SELECT monthly_bonus FROM bonus_lunar_config "
        "WHERE agent_key=:k AND an=2025 AND monthly_bonus>0 ORDER BY luna LIMIT 1",
        {"k": agent_key},
    )
    if rows and rows[0]["monthly_bonus"]:
        return rows[0]["monthly_bonus"]
    return DEFAULT_BONUS.get(agent_key, 0.0)


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


def _close_month(agent_key, db_agent, an, luna):
    """Îngheață luna: snapshot cu realizatul calculat în bonus_istoric (stare='inchis').

    Import lazy al orchestratorului din blueprint (depinde de Flask) — necesar doar
    când se cere închiderea; backfill-ul simplu rămâne fără dependență de Flask.
    """
    import json
    from blueprints.bonus import build_agent_month

    rec = queries.istoric_get(an, luna, agent_key)
    if rec and rec.get("stare") == "inchis":
        # Nu atinge închiderile manuale ale directorului.
        if rec.get("note") != "backfill istoric":
            return "manual-skip"
        # Snapshot de backfill — îl ștergem ca să-l regenerăm din config curent
        # (altfel build_agent_month ar întoarce snapshot-ul vechi, posibil cu bonus 0).
        queries.istoric_delete(an, luna, agent_key)
    out = build_agent_month(agent_key, db_agent, an, luna)
    if not out.get("kpis"):
        return "fara-obiective"
    queries.istoric_lock(an, luna, agent_key, json.dumps(out),
                         0.0, 1.0, "backfill istoric")
    return "inchis"


def main():
    ap = argparse.ArgumentParser(description="Backfill obiective bonus istorice")
    ap.add_argument("--an", type=int, default=2026)
    ap.add_argument("--luni", default="1-6", help="ex: 1-6 sau 1,2,3")
    ap.add_argument("--close", action="store_true",
                    help="închide lunile (snapshot înghețat cu realizat)")
    ap.add_argument("--dry-run", action="store_true", help="afișează fără a scrie")
    args = ap.parse_args()

    luni = _parse_luni(args.luni)
    # Doar agenții de teren (au db_agent cu un singur agent, fără '|').
    agents = [a for a in queries.bonus_agents(activ_only=True)
              if a["db_agent"] and "|" not in a["db_agent"]]

    print(f"Backfill an={args.an} luni={luni} close={args.close} "
          f"agenți={[a['agent_key'] for a in agents]}"
          f"{' (DRY-RUN)' if args.dry_run else ''}\n")

    for a in agents:
        # bonus_agents nu întoarce ponderile — le luăm din bonus_config complet.
        cfg = dict(query(
            "SELECT w_sales, w_margin, w_strategic, growth_pct FROM bonus_config "
            "WHERE agent_key=:k", {"k": a["agent_key"]})[0])
        mb = _monthly_bonus(a["agent_key"])

        for luna in luni:
            existing = queries.obiective(args.an, luna, a["agent_key"])
            # „Proper" = structura nouă (conține un rând vânzări). Seed-ul vechi
            # ad-hoc avea doar rânduri de brand cu target NULL — îl tratăm ca lipsă
            # și îl rescriem (save_obiective șterge+inserează, deci înlocuiește junk-ul).
            has_proper = any(r["tip"] == "vanzari" for r in existing)
            growth = cfg.get("growth_pct") or 0.20
            if has_proper:
                # Obiective ok — dar repară monthly_bonus dacă lipsește/0
                # (ex. pe prod unde seed-ul 2025 lipsea → backfill salvase 0).
                lc = queries.lunar_config(args.an, luna, a["agent_key"])
                if not args.dry_run and (not lc or not lc.get("monthly_bonus")):
                    queries.upsert_lunar_bonus(args.an, luna, a["agent_key"], mb, growth)
                    action = "fix-bonus"
                else:
                    action = "exists"
            else:
                kpis = _build_kpis(cfg, a["db_agent"], args.an, luna)
                if args.dry_run:
                    pond = round(sum(k["pondere"] for k in kpis) * 100)
                    print(f"  [dry ] {a['agent_key']:<8} {args.an}-{luna:02d}: "
                          f"bonus={mb:.0f} pond={pond}% "
                          f"vânz_target={kpis[0]['target']:,} ({len(kpis)} KPI)"
                          f"{' +close' if args.close else ''}")
                    continue
                queries.save_obiective(args.an, luna, a["agent_key"],
                                       mb, growth, kpis)
                action = "saved"

            if args.close and not args.dry_run:
                cstatus = _close_month(a["agent_key"], a["db_agent"], args.an, luna)
                print(f"  [{action}/{cstatus}] {a['agent_key']:<8} {args.an}-{luna:02d}")
            elif not args.dry_run:
                print(f"  [{action}] {a['agent_key']:<8} {args.an}-{luna:02d}")

    print("\nGata.")


if __name__ == "__main__":
    main()
