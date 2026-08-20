"""
Sezonalitate vanzari + capacitate de finantare a varfului de sezon.

Raspunde intrebarilor de business puse de owner (2026-08-20) folosind exclusiv
datele deja existente in torb.db. Scriptul e read-only: nu scrie nimic in baza.

Sectiuni:
  Q1  distributia valorica pe trimestre (2025 Q1-Q4, 2026 Q1-Q2) pe TT / Pharma / total
  Q2  lunile cu cele mai mici vanzari istorice + factura pe client TT si pe agent
  Q3  branduri contra-sezoniere (indice de sezonalitate lunar vs. firma)
  Q4  capacitate de finantare a dublarii stocului (din balantele P&L)
  Q5  prag de rentabilitate (breakeven) per agent in lunile de extrasezon
  Q6  discounturi acordate efectiv + conditii comerciale + praguri de marja
  Q8  plafoane de credit clienti vs. expunere in varf de sezon

Q7 (gestiunea marfii expirate/deteriorate) nu are suport de date: ERP-ul nu
exporta lot + data expirarii, iar retururile nu sunt marcate separat. Scriptul
raporteaza ce lipseste in loc sa estimeze.

Usage (din radacina proiectului):
    python etl/analyze_seasonality.py                 # raport complet, markdown la stdout
    python etl/analyze_seasonality.py --out docs/analysis/2026-08-20-sezonalitate.md
    python etl/analyze_seasonality.py --sectiuni q1,q2,q3
    python etl/analyze_seasonality.py --canale        # doar inventarul tip_client -> grup
"""

import argparse
import sqlite3
import sys
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"

LUNI = ["", "ian", "feb", "mar", "apr", "mai", "iun",
        "iul", "aug", "sep", "oct", "nov", "dec"]

# Lunile de extrasezon folosite pentru Q3/Q5. Iunie-august: sezonul slab de ceai.
LUNI_VARA = (6, 7, 8)
LUNI_VARF = (10, 11, 12)

# tip_client (valoarea bruta din ERP, uppercase) -> grup de canal.
# Orice valoare care nu apare aici intra in "NECLASIFICAT" si e listata explicit
# in raport, ca sa nu se ascunda cifre intr-un grup gresit. Corectiile se fac
# doar aici; rulati --canale pe baza reala inainte de a citi cifrele.
CANAL_GROUPS = {
    "HYPERMARKET":          "IKA",
    "SUPERMARKET":          "IKA",
    "CASH&CARRY":           "IKA",
    "CASH & CARRY":         "IKA",
    "MAGAZIN CASH&CARRY":   "IKA",
    "DISCOUNT":             "IKA",
    "FARMACIE":             "PHARMA",
    "DISTRUBUITOR PHARMA":  "PHARMA",
    "DISTRIBUITOR PHARMA":  "PHARMA",
    "PHARMA":               "PHARMA",
    "DISTRIBUITOR":         "DISTRIBUITOR",
    "DISTRIBUITOR FOOD":    "DISTRIBUITOR",
    "TT":                   "TT",
    "TRADITIONAL":          "TT",
    "MAGAZIN":              "TT",
    "MAGAZIN ALIMENTAR":    "TT",
    "ALIMENTARA":           "TT",
    "MINIMARKET":           "TT",
    "BENZINARIE MOL":       "TT",
    "HORECA":               "HORECA",
    "ONLINE":               "ONLINE",
    "EXPORT":               "EXPORT",
    "ALTI":                 "ALTELE",
    "ALTELE":               "ALTELE",
    "FARA TIP CLIENT":      "ALTELE",
}

ORDINE_GRUPURI = ["TT", "PHARMA", "IKA", "DISTRIBUITOR", "HORECA",
                  "ONLINE", "EXPORT", "ALTELE", "NECLASIFICAT"]

# Prefixe de cont din balanta (clasa 1-5) folosite la Q4. Semnul spune cum se
# citeste soldul final: +1 = sold debitor (activ), -1 = sold creditor (pasiv).
CONTURI_BILANT = [
    ("Disponibil banca",        ("512",),                       +1),
    ("Casa",                    ("531",),                       +1),
    ("Stoc marfa",              ("371", "381"),                 +1),
    ("Creante clienti",         ("411", "418"),                 +1),
    ("Avansuri furnizori",      ("409",),                       +1),
    ("Credite bancare curente", ("519",),                       -1),
    ("Credite termen lung",     ("162",),                       -1),
    ("Furnizori",               ("401", "403", "404", "408"),   -1),
]

OUT = []


def say(line=""):
    OUT.append(line)


def ron(v):
    """1234567.8 -> '1.234.568'. Valorile sunt in RON, fara zecimale."""
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".")


def pct(v, total):
    if not total:
        return "—"
    return f"{100.0 * v / total:.1f}%"


def table(header, rows):
    say("| " + " | ".join(header) + " |")
    say("|" + "|".join(["---"] * len(header)) + "|")
    for r in rows:
        say("| " + " | ".join(str(c) for c in r) + " |")
    say()


def grup_canal(tip_client):
    if tip_client is None:
        return "ALTELE"
    return CANAL_GROUPS.get(str(tip_client).strip().upper(), "NECLASIFICAT")


# Same rule as app/pnl_logic.resolve_cont: exact account first, then the longest
# mapped prefix of >= 3 chars, so analytic accounts (6221) follow their
# synthetic parent (622).
def resolve_cont(cont, mapping):
    if cont in mapping:
        return mapping[cont]
    for n in range(len(cont) - 1, 2, -1):
        if cont[:n] in mapping:
            return mapping[cont[:n]]
    return None


def has_table(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def lipsa(nume_tabel):
    say(f"> **Date indisponibile** — tabelul `{nume_tabel}` nu exista in baza. "
        f"Sectiune sarita.")
    say()


# --------------------------------------------------------------------------
# Inventarul canalelor — se ruleaza intotdeauna inaintea sectiunilor pe canal.
# --------------------------------------------------------------------------

def sectiune_canale(conn):
    say("## Inventar canale (tip_client → grup)")
    say()
    say("Maparea traieste in `CANAL_GROUPS` din `etl/analyze_seasonality.py`. "
        "Orice `tip_client` care nu e in mapare apare ca **NECLASIFICAT** — "
        "corectati maparea inainte de a folosi cifrele pe canal.")
    say()
    rows = conn.execute("""
        SELECT tip_client, COUNT(DISTINCT cod_client) AS nr_clienti,
               SUM(val_neta) AS val
        FROM tranzactii GROUP BY tip_client ORDER BY val DESC
    """).fetchall()
    total = sum(r["val"] or 0 for r in rows)
    out = []
    neclasificat = 0.0
    for r in rows:
        g = grup_canal(r["tip_client"])
        if g == "NECLASIFICAT":
            neclasificat += r["val"] or 0
        out.append([r["tip_client"] or "(gol)", g, r["nr_clienti"],
                    ron(r["val"]), pct(r["val"] or 0, total)])
    table(["tip_client (ERP)", "Grup", "Clienți", "Val. netă istorică", "% total"], out)
    if neclasificat:
        say(f"> ⚠ **{ron(neclasificat)} RON ({pct(neclasificat, total)}) "
            f"neclasificat** — completați `CANAL_GROUPS` și re-rulați.")
        say()


# --------------------------------------------------------------------------
# Q1 — distributia valorica pe trimestre
# --------------------------------------------------------------------------

def sectiune_q1(conn):
    say("## Q1. Cât a reprezentat fiecare trimestru (TT, Pharma, total firmă)")
    say()
    rows = conn.execute("""
        SELECT an, luna, tip_client, SUM(val_neta) AS val
        FROM tranzactii
        WHERE an IN (2024, 2025, 2026) AND luna BETWEEN 1 AND 12
        GROUP BY an, luna, tip_client
    """).fetchall()

    # (an, trimestru, grup) -> valoare; grupul "TOTAL" acumuleaza toata firma.
    q = defaultdict(float)
    for r in rows:
        trim = (r["luna"] - 1) // 3 + 1
        v = r["val"] or 0.0
        q[(r["an"], trim, grup_canal(r["tip_client"]))] += v
        q[(r["an"], trim, "TOTAL")] += v

    ani = sorted({a for (a, _, _) in q})
    for an in ani:
        trimestre = sorted({t for (a, t, _) in q if a == an})
        if not trimestre:
            continue
        say(f"### {an} " + ("(an complet)" if len(trimestre) == 4
                            else f"(parțial — Q{trimestre[0]}–Q{trimestre[-1]})"))
        say()
        grupuri = [g for g in ORDINE_GRUPURI
                   if any(q[(an, t, g)] for t in trimestre)]
        header = ["Segment"] + [f"Q{t}" for t in trimestre] + ["Total perioadă"]
        body = []
        for g in ["TOTAL"] + grupuri:
            eticheta = "**TOTAL FIRMĂ**" if g == "TOTAL" else g
            tot_g = sum(q[(an, t, g)] for t in trimestre)
            celule = []
            for t in trimestre:
                v = q[(an, t, g)]
                celule.append(f"{ron(v)}<br>{pct(v, tot_g)}")
            body.append([eticheta] + celule + [ron(tot_g)])
        table(header, body)

        if len(trimestre) == 4:
            say("**Cât de sezonieră e vânzarea** (abaterea față de 25%/trimestru "
                "— 0 pp = perfect liniar):")
            say()
            met = []
            for g in ["TOTAL"] + grupuri:
                vals = [q[(an, t, g)] for t in trimestre]
                tot_g = sum(vals)
                if not tot_g:
                    continue
                cote = [100.0 * v / tot_g for v in vals]
                abatere = max(abs(c - 25.0) for c in cote)
                amplitudine = (max(cote) / min(cote)) if min(cote) > 0 else 0
                verdict = ("liniar" if abatere < 5 else
                           "moderat sezonier" if abatere < 10 else
                           "puternic sezonier")
                met.append(["TOTAL FIRMĂ" if g == "TOTAL" else g,
                            f"Q{trimestre[cote.index(max(cote))]}",
                            f"{max(cote):.1f}%",
                            f"Q{trimestre[cote.index(min(cote))]}",
                            f"{min(cote):.1f}%",
                            f"{abatere:.1f} pp",
                            f"{amplitudine:.2f}×" if amplitudine else "—",
                            verdict])
            table(["Segment", "Trim. vârf", "% vârf", "Trim. minim", "% minim",
                   "Abatere max. vs 25%", "Vârf/minim", "Verdict"], met)


# --------------------------------------------------------------------------
# Q2 — lunile slabe + valoarea facturata pe client TT si pe agent
# --------------------------------------------------------------------------

def sectiune_q2(conn, top=15):
    say("## Q2. Lunile cu cele mai mici vânzări istorice")
    say()
    rows = conn.execute("""
        SELECT an, luna, SUM(val_neta) AS val
        FROM tranzactii WHERE luna BETWEEN 1 AND 12
        GROUP BY an, luna ORDER BY an, luna
    """).fetchall()
    if not rows:
        say("> Fără tranzacții în bază.")
        say()
        return []

    # O luna calendaristica intra in medie doar cu anii in care are date, ca sa
    # nu penalizeze lunile pe care anul curent nu le-a atins inca.
    per_luna = defaultdict(list)
    for r in rows:
        per_luna[r["luna"]].append((r["an"], r["val"] or 0.0))

    ani_completi = sorted({r["an"] for r in rows
                           if len({x["luna"] for x in rows if x["an"] == r["an"]}) == 12})
    say(f"Ani cu 12 luni de date: {', '.join(str(a) for a in ani_completi) or '—'}. "
        "Media lunară de mai jos folosește doar acești ani, ca lunile neatinse "
        "ale anului curent să nu falsifice clasamentul.")
    say()

    medii = {}
    for luna, serii in per_luna.items():
        vals = [v for (a, v) in serii if a in ani_completi] or [v for (_, v) in serii]
        medii[luna] = sum(vals) / len(vals)
    media_generala = sum(medii.values()) / len(medii)

    clasament = sorted(medii.items(), key=lambda kv: kv[1])
    body = []
    for rank, (luna, med) in enumerate(clasament, 1):
        detalii = " · ".join(f"{a}: {ron(v)}" for a, v in sorted(per_luna[luna]))
        body.append([rank, LUNI[luna], ron(med),
                     f"{100.0 * med / media_generala:.0f}%", detalii])
    table(["#", "Lună", "Medie istorică", "Indice vs. media anului", "Pe ani"], body)

    luni_slabe = [luna for luna, _ in clasament[:3]]
    say(f"**Cele mai slabe 3 luni: {', '.join(LUNI[m] for m in luni_slabe)}.**")
    say()

    ph = ",".join("?" * len(luni_slabe))
    say(f"### Valoarea facturată în {', '.join(LUNI[m] for m in luni_slabe)} — pe agent")
    say()
    ag = conn.execute(f"""
        SELECT agent, an, SUM(val_neta) AS val
        FROM tranzactii WHERE luna IN ({ph})
        GROUP BY agent, an ORDER BY agent, an
    """, luni_slabe).fetchall()
    per_agent = defaultdict(dict)
    ani = sorted({r["an"] for r in ag})
    for r in ag:
        per_agent[r["agent"] or "(fără agent)"][r["an"]] = r["val"] or 0.0
    body = []
    for agent, pe_an in sorted(per_agent.items(),
                               key=lambda kv: -sum(kv[1].values())):
        celule = [ron(pe_an.get(a)) for a in ani]
        nr_luni = len(luni_slabe)
        medie_lunara = sum(pe_an.values()) / (len(pe_an) * nr_luni) if pe_an else 0
        body.append([agent] + celule + [ron(medie_lunara)])
    table(["Agent"] + [str(a) for a in ani] + ["Medie / lună slabă"], body)

    say(f"### Valoarea facturată în {', '.join(LUNI[m] for m in luni_slabe)} — "
        f"top {top} clienți TT")
    say()
    cl = conn.execute(f"""
        SELECT client, cod_client, tip_client, agent,
               SUM(val_neta) AS val, COUNT(DISTINCT an || '-' || luna) AS luni_active
        FROM tranzactii WHERE luna IN ({ph})
        GROUP BY cod_client ORDER BY val DESC
    """, luni_slabe).fetchall()
    tt = [r for r in cl if grup_canal(r["tip_client"]) == "TT"]
    total_tt = sum(r["val"] or 0 for r in tt)
    body = []
    for r in tt[:top]:
        body.append([r["client"], r["agent"] or "—", ron(r["val"]),
                     pct(r["val"] or 0, total_tt), r["luni_active"],
                     ron((r["val"] or 0) / max(r["luni_active"], 1))])
    table(["Client TT", "Agent", "Total în lunile slabe", "% din TT",
           "Luni cu facturi", "Medie / lună"], body)
    say(f"**Total TT în lunile slabe (istoric cumulat): {ron(total_tt)} RON**, "
        f"pe {len(tt)} clienți TT activi.")
    say()
    return luni_slabe


# --------------------------------------------------------------------------
# Q3 — branduri contra-sezoniere
# --------------------------------------------------------------------------

def sectiune_q3(conn, prag_val=50000):
    say("## Q3. Branduri cu evoluție contra-sezonieră")
    say()
    say("Indice de sezonalitate = cota lunii în CA anuală a brandului ÷ 1/12. "
        "Indice 1.00 = luna e perfect medie pentru brandul respectiv. "
        "Un brand e **contra-sezonier** dacă indicele lui de vară "
        f"({'/'.join(LUNI[m] for m in LUNI_VARA)}) e peste 1 în timp ce firma e sub 1.")
    say()
    rows = conn.execute("""
        SELECT furnizor, luna, SUM(val_neta) AS val
        FROM tranzactii WHERE luna BETWEEN 1 AND 12
        GROUP BY furnizor, luna
    """).fetchall()
    per_brand = defaultdict(lambda: defaultdict(float))
    firma = defaultdict(float)
    for r in rows:
        per_brand[r["furnizor"] or "(fără brand)"][r["luna"]] += r["val"] or 0.0
        firma[r["luna"]] += r["val"] or 0.0

    total_firma = sum(firma.values())
    idx_firma = {m: (firma[m] / total_firma * 12) if total_firma else 0
                 for m in range(1, 13)}
    idx_firma_vara = sum(firma[m] for m in LUNI_VARA) / total_firma * 4 if total_firma else 0

    say(f"**Referință firmă** — indice vară: **{idx_firma_vara:.2f}**, "
        f"indice vârf ({'/'.join(LUNI[m] for m in LUNI_VARF)}): "
        f"**{sum(firma[m] for m in LUNI_VARF) / total_firma * 4:.2f}**")
    say()

    body, contra = [], []
    for brand, luni in sorted(per_brand.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(luni.values())
        if tot < prag_val:
            continue
        idx = {m: luni[m] / tot * 12 for m in range(1, 13)}
        iv = sum(luni[m] for m in LUNI_VARA) / tot * 4
        ivf = sum(luni[m] for m in LUNI_VARF) / tot * 4
        semn = "✅ contra-sezonier" if iv > 1.0 and idx_firma_vara < 1.0 else (
               "≈ neutru" if 0.9 <= iv <= 1.1 else "sezonier (vară slabă)")
        if iv > 1.0 and idx_firma_vara < 1.0:
            contra.append((brand, iv, tot))
        body.append([brand, ron(tot), pct(tot, total_firma),
                     f"{iv:.2f}", f"{ivf:.2f}",
                     LUNI[max(idx, key=idx.get)], LUNI[min(idx, key=idx.get)], semn])
    table(["Brand", "CA istorică", "% portofoliu", "Indice vară", "Indice Q4",
           "Luna vârf", "Luna minim", "Verdict"], body)

    if contra:
        say("**Brandurile care compensează vara** (indice vară > 1 pe o firmă cu "
            "vara sub medie): " +
            ", ".join(f"{b} ({i:.2f})" for b, i, _ in sorted(contra, key=lambda x: -x[1])))
    else:
        say("**Niciun brand din portofoliu nu are indice de vară peste 1** — "
            "scăderea de vară nu e compensată intern de mixul actual.")
    say()

    say("### Matricea lunară a indicilor (branduri peste "
        f"{ron(prag_val)} RON CA istorică)")
    say()
    body = [["**FIRMĂ**"] + [f"{idx_firma[m]:.2f}" for m in range(1, 13)]]
    for brand, luni in sorted(per_brand.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(luni.values())
        if tot < prag_val:
            continue
        body.append([brand] + [f"{luni[m] / tot * 12:.2f}" for m in range(1, 13)])
    table(["Brand"] + LUNI[1:], body)


# --------------------------------------------------------------------------
# Q4 — capacitatea de a finanta dublarea stocului
# --------------------------------------------------------------------------

def _ultima_balanta(conn, entitate):
    r = conn.execute("""
        SELECT an, luna FROM pnl_balante_raw WHERE entitate=?
        ORDER BY an DESC, luna DESC LIMIT 1
    """, (entitate,)).fetchone()
    return (r["an"], r["luna"]) if r else (None, None)


def sectiune_q4(conn):
    say("## Q4. Putem finanța dublarea stocului în avans?")
    say()
    if not has_table(conn, "pnl_balante_raw"):
        lipsa("pnl_balante_raw")
        return
    entitati = [r["entitate"] for r in conn.execute(
        "SELECT DISTINCT entitate FROM pnl_balante_raw ORDER BY entitate")]
    if not entitati:
        say("> Nu există balanțe încărcate. Încărcați balanțele din "
            "**Actualizare → P&L** și re-rulați.")
        say()
        return

    for ent in entitati:
        an, luna = _ultima_balanta(conn, ent)
        say(f"### {ent} — balanța {LUNI[luna]} {an}")
        say()
        rows = conn.execute("""
            SELECT cont, dencont, sfd, sfc FROM pnl_balante_raw
            WHERE entitate=? AND an=? AND luna=?
        """, (ent, an, luna)).fetchall()

        pozitii = {}
        for eticheta, prefixe, semn in CONTURI_BILANT:
            s = 0.0
            for r in rows:
                cont = str(r["cont"] or "")
                if cont.startswith(prefixe):
                    s += (r["sfd"] or 0.0) if semn > 0 else (r["sfc"] or 0.0)
            pozitii[eticheta] = s
        table(["Poziție bilanțieră", "Sold final (RON)"],
              [[k, ron(v)] for k, v in pozitii.items()])

        stoc = pozitii["Stoc marfa"]
        numerar = pozitii["Disponibil banca"] + pozitii["Casa"]
        credite = pozitii["Credite bancare curente"] + pozitii["Credite termen lung"]
        furnizori = pozitii["Furnizori"]
        creante = pozitii["Creante clienti"]

        say(f"- **Nevoie de finanțare pentru dublarea stocului: {ron(stoc)} RON** "
            f"(stoc curent × 1).")
        say(f"- Resurse proprii lichide azi: **{ron(numerar)} RON** "
            f"({pct(numerar, stoc)} din nevoie).")
        say(f"- Capital de lucru net (creanțe + stoc − furnizori): "
            f"**{ron(creante + stoc - furnizori)} RON**.")
        say(f"- Datorii bancare trase în acest moment: **{ron(credite)} RON**. "
            "Plafonul contractat *nu* există în balanță — vezi nota de mai jos.")
        deficit = stoc - numerar
        if deficit > 0:
            say(f"- ⚠ **Deficit de acoperit: {ron(deficit)} RON** din linie de "
                f"credit nefolosită, prelungire de termen la furnizori sau "
                f"accelerarea încasărilor (creanțe deschise: {ron(creante)} RON).")
        else:
            say("- ✅ Numerarul curent acoperă singur dublarea stocului.")
        say()

    say("> **Limita datelor:** balanța arată doar *cât s-a tras* (sold 519/162), "
        "nu **plafonul contractat** al liniilor de credit și nici covenantele. "
        "Plafoanele aprobate de bănci nu există nicăieri în sistem — trebuie "
        "introduse manual pentru un răspuns complet. Scadențarul furnizorilor "
        "externi (când devin exigibile facturile de import) nu e nici el în "
        "bază: `solduri_neincasate` acoperă doar creanțele, nu și datoriile.")
    say()


# --------------------------------------------------------------------------
# Q5 — breakeven per agent in extrasezon
# --------------------------------------------------------------------------

def sectiune_q5(conn, an=2026):
    say(f"## Q5. Prag de rentabilitate per agent în extrasezon "
        f"({'/'.join(LUNI[m] for m in LUNI_VARA)})")
    say()
    if not has_table(conn, "pnl_balante_raw"):
        lipsa("pnl_balante_raw")
        return

    # Costuri fixe lunare = OPEX mapat pe clasa 6, mediat pe lunile incarcate.
    # rulld = rulajul debitor AL LUNII (rulcd e cumulatul de la inceputul anului);
    # aceeasi conventie ca app/pnl_logic._entity_monthly, altfel lunile se dubleaza.
    mapping = {r["cont"]: r["pnl_line"] for r in conn.execute(
        "SELECT cont, pnl_line FROM pnl_mapping_conturi WHERE categorie='opex'")}
    rows = conn.execute("""
        SELECT luna, cont, rulld FROM pnl_balante_raw
        WHERE entitate='torb' AND an=?
    """, (an,)).fetchall()
    if not rows:
        say(f"> Fără balanțe {an} pentru entitatea `torb`. "
            "Încărcați-le și re-rulați.")
        say()
        return

    per_luna = defaultdict(float)
    per_linie = defaultdict(float)
    for r in rows:
        linie = resolve_cont(str(r["cont"] or ""), mapping)
        if linie is None:
            continue
        per_luna[r["luna"]] += r["rulld"] or 0.0
        per_linie[linie] += r["rulld"] or 0.0
    if not per_luna:
        say(f"> Balanțele {an} nu conțin conturi mapate pe OPEX.")
        say()
        return
    luni_incarcate = sorted(per_luna)
    opex_lunar = sum(per_luna.values()) / len(luni_incarcate)

    say(f"Structura de costuri {an}, lunile "
        f"{', '.join(LUNI[m] for m in luni_incarcate)} "
        f"(rulaj debitor propriu al lunii, conturi clasa 6 mapate pe OPEX):")
    say()
    table(["Linie OPEX", f"Cumulat {an}", "Medie / lună"],
          [[k, ron(v), ron(v / len(luni_incarcate))]
           for k, v in sorted(per_linie.items(), key=lambda kv: -kv[1])] +
          [["**TOTAL OPEX**", f"**{ron(sum(per_linie.values()))}**",
            f"**{ron(opex_lunar)}**"]])

    # Marja bruta procentuala per agent, pe anul curent.
    ag = conn.execute("""
        SELECT agent, SUM(val_neta) AS val, SUM(marja_bruta) AS marja
        FROM tranzactii WHERE an=? GROUP BY agent
    """, (an,)).fetchall()
    total_val = sum(r["val"] or 0 for r in ag)
    if not total_val:
        say(f"> Fără vânzări {an}.")
        say()
        return

    # Vanzarile reale de vara, pentru comparatie cu pragul.
    vara = {r["agent"]: r["val"] or 0.0 for r in conn.execute("""
        SELECT agent, SUM(val_neta) / COUNT(DISTINCT an || '-' || luna) AS val
        FROM tranzactii WHERE luna IN (?, ?, ?) GROUP BY agent
    """, LUNI_VARA)}

    say(f"**Alocarea costurilor fixe:** proporțional cu cota fiecărui agent în "
        f"CA {an} (regula cea mai simplă defensabilă — sistemul nu ține costuri "
        f"pe centru de profit). Prag = OPEX alocat ÷ marja brută %.")
    say()
    body = []
    for r in sorted(ag, key=lambda x: -(x["val"] or 0)):
        val, marja = r["val"] or 0.0, r["marja"] or 0.0
        if not val:
            continue
        rata = marja / val
        cota = val / total_val
        opex_alocat = opex_lunar * cota
        prag = opex_alocat / rata if rata > 0 else None
        real = vara.get(r["agent"], 0.0)
        acoperire = (real / prag) if prag else None
        body.append([
            r["agent"] or "(fără agent)", f"{100 * cota:.1f}%",
            f"{100 * rata:.1f}%", ron(opex_alocat),
            ron(prag) if prag else "—", ron(real),
            f"{100 * acoperire:.0f}%" if acoperire else "—",
            ("✅ peste prag" if acoperire and acoperire >= 1 else
             "⚠ sub prag" if acoperire else "—"),
        ])
    table(["Agent", "Cotă CA", "Marjă brută %", "OPEX alocat / lună",
           "Prag rentabilitate / lună", "Vânzare medie vară (istoric)",
           "Acoperire", "Verdict"], body)

    rata_firma = sum(r["marja"] or 0 for r in ag) / total_val
    say(f"**Prag pe total firmă: {ron(opex_lunar / rata_firma)} RON / lună** "
        f"la marja brută medie de {100 * rata_firma:.1f}%.")
    say()
    say("> **Limita datelor:** OPEX-ul e tratat integral ca fix. Partea variabilă "
        "(bonusuri de vânzări, transport pe volum) ar coborî pragul; "
        "defalcarea fix/variabil nu există în mapare — e o decizie de owner.")
    say()


# --------------------------------------------------------------------------
# Q6 — discounturi
# --------------------------------------------------------------------------

def sectiune_q6(conn, an=2026):
    say("## Q6. Discount maxim acordabil în teren")
    say()
    say("### Ce s-a acordat efectiv (din facturi)")
    say()
    rows = conn.execute("""
        SELECT tip_client, agent,
               SUM(discount_val) AS disc, SUM(val_bruta) AS brut,
               MAX(discount_pct) AS maxim,
               SUM(CASE WHEN discount_pct > 0 THEN val_bruta ELSE 0 END) AS brut_cu_disc
        FROM tranzactii WHERE an=? GROUP BY tip_client, agent
    """, (an,)).fetchall()
    per_grup = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for r in rows:
        g = per_grup[grup_canal(r["tip_client"])]
        g[0] += r["disc"] or 0.0
        g[1] += r["brut"] or 0.0
        g[2] = max(g[2], r["maxim"] or 0.0)
        g[3] += r["brut_cu_disc"] or 0.0
    table(["Canal", f"Discount acordat {an}", "Valoare brută",
           "Discount mediu %", "Discount maxim pe o linie",
           "% din CA cu discount"],
          [[g, ron(v[0]), ron(v[1]),
            f"{100 * v[0] / v[1]:.1f}%" if v[1] else "—",
            f"{v[2]:.1f}%", pct(v[3], v[1])]
           for g, v in sorted(per_grup.items(), key=lambda kv: -kv[1][1])])

    say("### Discount efectiv pe brand (canalul DISTRIBUITOR)")
    say()
    rows = conn.execute("""
        SELECT furnizor, tip_client, SUM(discount_val) AS disc,
               SUM(val_bruta) AS brut, MAX(discount_pct) AS maxim
        FROM tranzactii WHERE an=? GROUP BY furnizor, tip_client
    """, (an,)).fetchall()
    per_brand = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        if grup_canal(r["tip_client"]) != "DISTRIBUITOR":
            continue
        b = per_brand[r["furnizor"] or "(fără brand)"]
        b[0] += r["disc"] or 0.0
        b[1] += r["brut"] or 0.0
        b[2] = max(b[2], r["maxim"] or 0.0)
    if per_brand:
        table(["Brand", "Discount acordat", "Valoare brută", "Mediu %", "Maxim pe linie"],
              [[b, ron(v[0]), ron(v[1]),
                f"{100 * v[0] / v[1]:.1f}%" if v[1] else "—", f"{v[2]:.1f}%"]
               for b, v in sorted(per_brand.items(), key=lambda kv: -kv[1][1])])
    else:
        say("> Niciun client clasificat DISTRIBUITOR în anul selectat.")
        say()

    say("### Regula formală din sistem")
    say()
    if has_table(conn, "pricing_config"):
        praguri = defaultdict(dict)
        for r in conn.execute(
                "SELECT gama, cheie, valoare FROM pricing_config "
                "WHERE cheie LIKE 'marja%'"):
            praguri[r["gama"] or "(global)"][r["cheie"]] = r["valoare"]
        for gama, chei in sorted(praguri.items()):
            say(f"- `{gama}` — marjă minimă **{chei.get('marja_minima_pct', '—')}%**, "
                f"sub **{chei.get('marja_aprobare_pct', '—')}%** e necesară "
                f"aprobarea directorului.")
        say()
        say("Acestea sunt singurele praguri formalizate în sistem: nu există un "
            "câmp „discount maxim per agent\u201d nicăieri — limita reală e "
            "marja rămasă după discount.")
        say()
    if has_table(conn, "conditii_comerciale"):
        rows = conn.execute("""
            SELECT cod_client, furnizor, tip_valoare, periodicitate,
                   SUM(valoare) AS val, COUNT(*) AS n
            FROM conditii_comerciale WHERE an=? AND tip_valoare='pct'
            GROUP BY cod_client ORDER BY val DESC LIMIT 25
        """, (an,)).fetchall()
        if rows:
            say(f"**Condiții comerciale {an} — % pe total portofoliu, per client** "
                "(top 25). `furnizor` gol = condiția se aplică la tot portofoliul "
                "clientului, nu pe brand:")
            say()
            table(["Cod client", "Furnizor (brand)", "% total", "Nr. rânduri"],
                  [[r["cod_client"], r["furnizor"] or "**toate brandurile**",
                    f"{r['val']:.2f}%", r["n"]] for r in rows])
            pe_brand = conn.execute("""
                SELECT COUNT(*) AS n FROM conditii_comerciale
                WHERE an=? AND furnizor IS NOT NULL AND furnizor <> ''
            """, (an,)).fetchone()["n"]
            total_cc = conn.execute(
                "SELECT COUNT(*) AS n FROM conditii_comerciale WHERE an=?",
                (an,)).fetchone()["n"]
            say(f"> **{pe_brand} din {total_cc}** condiții sunt definite pe brand; "
                f"restul sunt procent unic pe **tot portofoliul** clientului.")
            say()


# --------------------------------------------------------------------------
# Q8 — plafoane de credit clienti
# --------------------------------------------------------------------------

def sectiune_q8(conn, top=25):
    say("## Q8. Cu cât putem majora plafoanele de credit în vârf de sezon")
    say()
    if not has_table(conn, "solduri_neincasate"):
        lipsa("solduri_neincasate")
        return
    rows = conn.execute("""
        SELECT codcli, numecli, numeag, MAX(plafon) AS plafon,
               SUM(sumdeincas) AS expunere,
               SUM(CASE WHEN julianday('now') - julianday(datadl)
                        > COALESCE(term_pl_cl, 0) THEN sumdeincas ELSE 0 END) AS restant,
               MAX(COALESCE(term_pl_cl, 0)) AS termen
        FROM solduri_neincasate
        GROUP BY codcli
    """).fetchall()
    if not rows:
        say("> Snapshot-ul de solduri e gol. Încărcați raportul ERP și re-rulați.")
        say()
        return

    # Uplift-ul de varf: cat creste facturarea in oct-dec fata de media lunara.
    luni = {r["luna"]: r["val"] or 0.0 for r in conn.execute("""
        SELECT luna, SUM(val_neta) / COUNT(DISTINCT an) AS val
        FROM tranzactii WHERE luna BETWEEN 1 AND 12 GROUP BY luna
    """)}
    media = sum(luni.values()) / 12 if luni else 0
    varf = max((luni.get(m, 0) for m in LUNI_VARF), default=0)
    uplift = (varf / media) if media else 1.0
    say(f"**Factorul de vârf: {uplift:.2f}×** — luna de vârf facturează de "
        f"{uplift:.2f} ori media lunară. Plafonul necesar în vârf ≈ "
        f"expunerea curentă × {uplift:.2f}, corectat cu termenul de plată.")
    say()

    body, nevoie_totala = [], 0.0
    for r in sorted(rows, key=lambda x: -(x["expunere"] or 0))[:top]:
        plafon = r["plafon"] or 0.0
        exp = r["expunere"] or 0.0
        restant = r["restant"] or 0.0
        bun_platnic = restant <= 0
        nevoie = exp * uplift
        delta = nevoie - plafon if plafon else None
        if bun_platnic and delta and delta > 0:
            nevoie_totala += delta
        body.append([
            r["numecli"], r["numeag"] or "—", r["termen"],
            ron(plafon) if plafon else "**fără plafon**", ron(exp),
            pct(exp, plafon) if plafon else "—",
            ron(restant) if restant else "0",
            "✅ bun platnic" if bun_platnic else "⛔ are restanțe",
            ron(nevoie),
            # Majorarea se propune doar pentru buni platnici; pentru cei cu
            # restante depasirea de plafon e o problema de incasare, nu de plafon.
            ("—" if not plafon else
             "n/a (restanțe)" if not bun_platnic else
             ron(delta) if delta and delta > 0 else "0"),
        ])
    table(["Client", "Agent", "Termen (zile)", "Plafon", "Expunere azi",
           "Grad de utilizare", "Restant", "Comportament",
           f"Plafon necesar la {uplift:.2f}×", "Majorare necesară"], body)

    say(f"**Majorare totală necesară pentru clienții buni platnici din top {top}: "
        f"{ron(nevoie_totala)} RON.**")
    say()
    fara_plafon = sum(1 for r in rows if not (r["plafon"] or 0))
    say(f"> {fara_plafon} din {len(rows)} clienți cu sold deschis nu au plafon "
        "setat în ERP — pentru ei majorarea nu se poate cuantifica, iar limita "
        "de facto e decizia ad-hoc de la livrare.")
    say()


# --------------------------------------------------------------------------
# Q7 — fara suport de date
# --------------------------------------------------------------------------

def sectiune_q7(conn):
    say("## Q7. Marfa expirată / deteriorată în extrasezon")
    say()
    say("**Nu există date pentru un răspuns cantitativ.** Ce lipsește:")
    say()
    say("- ERP-ul nu exportă **lot + data expirării** (BBD) — nici pe `stoc`, "
        "nici pe `tranzactii`. Fără ele nu se poate calcula stocul cu risc, "
        "nu se poate face FEFO și nu se poate estima expunerea la expirare. "
        "Este item deschis în `docs/BACKLOG.md` §Aprovizionare "
        "(deciziile 12+13, o singură implementare).")
    say("- **Retururile nu sunt marcate** ca atare: liniile de storno intră în "
        "`tranzactii` ca valori negative, fără un motiv (expirat / deteriorat / "
        "comercial), deci nu pot fi separate de retururile obișnuite.")
    say("- Stocul din **depozitul distribuitorului și din raftul magazinului** "
        "(sell-out) nu ajunge deloc în sistem — vizibilitatea Torb se oprește la "
        "factura de ieșire (sell-in).")
    say()
    if has_table(conn, "tranzactii"):
        r = conn.execute("""
            SELECT SUM(val_neta) AS val, COUNT(*) AS n
            FROM tranzactii WHERE val_neta < 0
        """).fetchone()
        say(f"Singurul proxy măsurabil azi — linii cu valoare negativă "
            f"(storno + retururi, motive amestecate): **{r['n']} linii, "
            f"{ron(r['val'])} RON** pe tot istoricul.")
        say()
        rows = conn.execute("""
            SELECT luna, SUM(val_neta) AS val, COUNT(*) AS n
            FROM tranzactii WHERE val_neta < 0 AND luna BETWEEN 1 AND 12
            GROUP BY luna ORDER BY luna
        """).fetchall()
        if rows:
            table(["Lună", "Linii negative", "Valoare"],
                  [[LUNI[r["luna"]], r["n"], ron(r["val"])] for r in rows])


# --------------------------------------------------------------------------

SECTIUNI = {
    "q1": sectiune_q1,
    "q2": sectiune_q2,
    "q3": sectiune_q3,
    "q4": sectiune_q4,
    "q5": sectiune_q5,
    "q6": sectiune_q6,
    "q7": sectiune_q7,
    "q8": sectiune_q8,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--out", help="scrie raportul markdown în fișier")
    ap.add_argument("--sectiuni", default="all",
                    help="listă separată prin virgulă: q1,q2,... (implicit: toate)")
    ap.add_argument("--canale", action="store_true",
                    help="doar inventarul tip_client → grup")
    ap.add_argument("--an", type=int, default=2026,
                    help="anul curent pentru Q5/Q6 (implicit 2026)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if not has_table(conn, "tranzactii"):
        print(f"EROARE: {args.db} nu conține tabelul `tranzactii`.", file=sys.stderr)
        return 1

    say("# Sezonalitate vânzări & finanțarea vârfului de sezon")
    say()
    say(f"Generat de `etl/analyze_seasonality.py` din `{args.db}`. "
        "Toate valorile sunt **valoare netă (RON)**, fără TVA.")
    say()

    sectiune_canale(conn)
    if not args.canale:
        cerute = (list(SECTIUNI) if args.sectiuni == "all"
                  else [s.strip().lower() for s in args.sectiuni.split(",")])
        for cheie in cerute:
            fn = SECTIUNI.get(cheie)
            if fn is None:
                print(f"AVERTISMENT: secțiune necunoscută '{cheie}'", file=sys.stderr)
                continue
            if cheie in ("q5", "q6"):
                fn(conn, args.an)
            else:
                fn(conn)

    text = "\n".join(OUT)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Scris: {args.out}")
    else:
        print(text)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
