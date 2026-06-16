from db import query, get_db


def _write(sql, params=None):
    """Execută un singur statement de scriere (INSERT/UPDATE/DELETE) cu commit.

    Proiectul nu are un helper de scriere în db.py — scrierile folosesc get_db()
    (conexiune nouă; caller-ul face commit + close). Vezi app/queries/export.py.
    """
    db = get_db()
    try:
        db.execute(sql, params or {})
        db.commit()
    finally:
        db.close()


def _agent_in(db_agent):
    """Construiește un filtru SQL pe tranzactii.agent dintr-un db_agent care
    poate conține mai mulți agenți separați prin '|' (ex. online).
    Returnează (fragment_sql, params_dict)."""
    parts = [p.strip() for p in (db_agent or "").split("|") if p.strip()]
    if not parts:
        return ("1=0", {})
    keys = [f"a{i}" for i in range(len(parts))]
    frag = "LOWER(agent) IN (" + ",".join(f"LOWER(:{k})" for k in keys) + ")"
    return (frag, {k: v for k, v in zip(keys, parts)})


def bonus_team():
    return query("""
        SELECT employee_id, nume, rol, activ,
            bonus_target_lunar_ron, bonus_target_trim_ron, observatii
        FROM echipa WHERE activ = 1
        ORDER BY bonus_target_lunar_ron DESC
    """)


def bonus_agents(activ_only=True):
    sql = ("SELECT agent_key, db_agent, tip_agent, growth_pct, activ "
           "FROM bonus_config")
    if activ_only:
        sql += " WHERE activ = 1"
    sql += " ORDER BY agent_key"
    return query(sql)


def lunar_config(an, luna, agent_key):
    rows = query(
        "SELECT monthly_bonus, growth_pct FROM bonus_lunar_config "
        "WHERE an=:an AND luna=:luna AND agent_key=:k",
        {"an": an, "luna": luna, "k": agent_key})
    return rows[0] if rows else None


def obiective(an, luna, agent_key):
    return query(
        "SELECT id, tip, referinta, target_valoare AS target, target_unitate AS unitate, "
        "       pondere, realizat_manual "
        "FROM bonus_obiective_strategice "
        "WHERE an=:an AND luna=:luna AND agent_key=:k "
        "ORDER BY id",
        {"an": an, "luna": luna, "k": agent_key})


def payout_grid(agent_key):
    rows = query(
        "SELECT threshold, multiplier FROM bonus_payout_grid "
        "WHERE agent_key=:k ORDER BY threshold", {"k": agent_key})
    if not rows:
        rows = query(
            "SELECT threshold, multiplier FROM bonus_payout_grid "
            "WHERE agent_key='_default' ORDER BY threshold")
    return [(r["threshold"], r["multiplier"]) for r in rows]


def realizat_auto(db_agent, an, luna):
    """Realizat lunar auto din tranzactii: vânzări, marjă, nr. clienți activi."""
    frag, params = _agent_in(db_agent)
    params.update({"an": an, "luna": luna})
    rows = query(
        f"SELECT COALESCE(SUM(val_neta),0) AS vanzari, "
        f"       COALESCE(SUM(marja_bruta),0) AS marja, "
        f"       COUNT(DISTINCT cod_client) AS clienti "
        f"FROM tranzactii WHERE {frag} AND an=:an AND luna=:luna", params)
    r = rows[0]
    return {"vanzari": r["vanzari"], "marja": r["marja"], "clienti": r["clienti"]}


def realizat_brand(db_agent, furnizor, an, luna):
    frag, params = _agent_in(db_agent)
    params.update({"an": an, "luna": luna, "f": furnizor})
    rows = query(
        f"SELECT COALESCE(SUM(val_neta),0) AS vn FROM tranzactii "
        f"WHERE {frag} AND furnizor=:f AND an=:an AND luna=:luna", params)
    return rows[0]["vn"]


def py_baseline(db_agent, an, luna):
    """Baseline anul trecut aceeași lună: vânzări, marjă, clienți + per-brand."""
    py = an - 1
    base = realizat_auto(db_agent, py, luna)
    frag, params = _agent_in(db_agent)
    params.update({"an": py, "luna": luna})
    brand_rows = query(
        f"SELECT furnizor, COALESCE(SUM(val_neta),0) AS vn FROM tranzactii "
        f"WHERE {frag} AND an=:an AND luna=:luna GROUP BY furnizor", params)
    base["brand"] = {r["furnizor"]: r["vn"] for r in brand_rows}
    return base


_NOI_GAMA_CTE = """
WITH luna_clienti AS (
  SELECT DISTINCT cod_client, client FROM tranzactii
  WHERE {frag} AND furnizor=:gama AND an=:an AND luna=:luna
)
SELECT {select}
FROM luna_clienti lc
WHERE NOT EXISTS (
  SELECT 1 FROM tranzactii t2
  WHERE t2.cod_client = lc.cod_client AND t2.furnizor = :gama
    AND t2.data_dl >= date(:month_start, '-24 months')
    AND t2.data_dl <  :month_start
)
"""


def _noi_gama_params(db_agent, gama, an, luna):
    frag, params = _agent_in(db_agent)
    params.update({"gama": gama, "an": an, "luna": luna,
                   "month_start": f"{an}-{luna:02d}-01"})
    return frag, params


def clienti_noi_gama_count(db_agent, gama, an, luna):
    frag, params = _noi_gama_params(db_agent, gama, an, luna)
    sql = _NOI_GAMA_CTE.format(frag=frag, select="COUNT(*) AS n")
    return query(sql, params)[0]["n"]


def clienti_noi_gama_list(db_agent, gama, an, luna):
    frag, params = _noi_gama_params(db_agent, gama, an, luna)
    sql = _NOI_GAMA_CTE.format(frag=frag, select="lc.cod_client, lc.client")
    sql += " ORDER BY lc.client"
    return query(sql, params)


def save_obiective(an, luna, agent_key, monthly_bonus, growth_pct, kpis):
    """Upsert config lunar + înlocuiește toate rândurile KPI pentru (an,luna,agent).

    Folosește o singură conexiune pentru a face delete+insert tranzacțional.
    """
    db = get_db()
    try:
        db.execute(
            "INSERT INTO bonus_lunar_config (an, luna, agent_key, monthly_bonus, growth_pct) "
            "VALUES (:an,:luna,:k,:mb,:g) "
            "ON CONFLICT(an,luna,agent_key) DO UPDATE SET "
            "  monthly_bonus=excluded.monthly_bonus, growth_pct=excluded.growth_pct",
            {"an": an, "luna": luna, "k": agent_key, "mb": monthly_bonus, "g": growth_pct})
        db.execute(
            "DELETE FROM bonus_obiective_strategice "
            "WHERE an=:an AND luna=:luna AND agent_key=:k",
            {"an": an, "luna": luna, "k": agent_key})
        for kpi in kpis:
            db.execute(
                "INSERT INTO bonus_obiective_strategice "
                "(an, luna, agent_key, tip, referinta, target_valoare, target_unitate, "
                " pondere, realizat_manual) "
                "VALUES (:an,:luna,:k,:tip,:ref,:tv,:un,:pond,:rm)",
                {"an": an, "luna": luna, "k": agent_key,
                 "tip": kpi["tip"], "ref": kpi.get("referinta"),
                 "tv": kpi.get("target"), "un": kpi.get("unitate", "ron"),
                 "pond": kpi.get("pondere", 0), "rm": kpi.get("realizat_manual")})
        db.commit()
    finally:
        db.close()


def istoric_get(an, luna, agent_key):
    rows = query(
        "SELECT lunar_data, penalty_pct, grad_incasare, stare, inchis_la, note "
        "FROM bonus_istoric WHERE an=:an AND luna=:luna AND agent_key=:k",
        {"an": an, "luna": luna, "k": agent_key})
    return rows[0] if rows else None


def istoric_lock(an, luna, agent_key, lunar_data, penalty, grad_incasare, note):
    _write(
        "INSERT INTO bonus_istoric "
        "(an, luna, agent_key, lunar_data, penalty_pct, grad_incasare, stare, "
        " inchis_la, note) "
        "VALUES (:an,:luna,:k,:ld,:p,:gi,'inchis',datetime('now','localtime'),:n) "
        "ON CONFLICT(an,luna,agent_key) DO UPDATE SET "
        "  lunar_data=excluded.lunar_data, penalty_pct=excluded.penalty_pct, "
        "  grad_incasare=excluded.grad_incasare, stare='inchis', "
        "  inchis_la=excluded.inchis_la, note=excluded.note",
        {"an": an, "luna": luna, "k": agent_key, "ld": lunar_data,
         "p": penalty, "gi": grad_incasare, "n": note})


def add_agent(agent_key, db_agent, tip_agent="field"):
    _write(
        "INSERT INTO bonus_config (agent_key, db_agent, tip_agent, activ) "
        "VALUES (:k,:d,:t,1) "
        "ON CONFLICT(agent_key) DO UPDATE SET db_agent=excluded.db_agent, "
        "  tip_agent=excluded.tip_agent, activ=1",
        {"k": agent_key, "d": db_agent, "t": tip_agent})


def set_agent_active(agent_key, activ):
    _write("UPDATE bonus_config SET activ=:a WHERE agent_key=:k",
           {"a": int(activ), "k": agent_key})


def field_agents_in_tranzactii():
    """Agenți de teren prezenți în tranzactii dar nu încă în bonus_config."""
    return query("""
        SELECT DISTINCT t.agent FROM tranzactii t
        WHERE t.agent NOT IN ('EMAG','SITE','TRENDYOL','ALTEX')
          AND LOWER(t.agent) NOT IN (
              SELECT LOWER(db_agent) FROM bonus_config WHERE db_agent IS NOT NULL)
        ORDER BY t.agent
    """)
