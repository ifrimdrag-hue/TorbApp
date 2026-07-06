from db import query, get_db
from queries._shared import current_year


def preturi_catalog(an=None, furnizor=None, search=None, fara_pret=False, sub_marja=None):
    if an is None:
        an = current_year()
    """Full pricing view: landing cost + selling price + margins."""
    filters, params = ["1=1"], {"an": an}
    if furnizor:
        filters.append("p.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if search:
        filters.append("(p.sku LIKE :s OR p.descriere LIKE :s OR CAST(cp.cod AS TEXT) LIKE :s)")
        params['s'] = f'%{search}%'
    if fara_pret:
        filters.append("pv.pret_vanzare_ron IS NULL")
    where = " AND ".join(filters)
    rows = query(f"""
        SELECT p.sku, cp.cod AS cod_produs, p.descriere, p.furnizor, p.brand, p.categorie,
               p.gramaj, p.buc_cutie, p.ean, p.tva_pct, p.hs_code,
               p.taxa_vamala_mfn_pct, p.taxa_vamala_pct,
               p.origine, p.tara_origine,
               cl.moneda, cl.pret_achizitie_valuta, cl.curs_ron,
               cl.pret_achizitie_ron, cl.transport_pct,
               cl.taxa_vamala_pct AS lc_taxa_vamala_pct,
               cl.alte_costuri_ron, cl.landing_cost_ron,
               pv.pret_vanzare_ron,
               ROUND(pv.pret_vanzare_ron - cl.landing_cost_ron, 4) AS marja_bruta_ron,
               ROUND((pv.pret_vanzare_ron - cl.landing_cost_ron)
                     / NULLIF(pv.pret_vanzare_ron, 0) * 100, 2) AS marja_bruta_pct,
               rs.curs_ron AS curs_default
        FROM produse p
        LEFT JOIN v_sku_cod cp ON cp.sku = p.sku
        LEFT JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
        LEFT JOIN preturi_vanzare pv ON pv.sku = p.sku
                  AND pv.an = :an AND pv.cod_client IS NULL AND pv.activ = 1
        LEFT JOIN rate_schimb rs ON rs.an = :an AND rs.moneda = cl.moneda
        WHERE {where} AND p.activ = 1
        ORDER BY p.furnizor, p.sku
    """, params)
    if sub_marja is not None:
        rows = [r for r in rows
                if r['marja_bruta_pct'] is not None and r['marja_bruta_pct'] < sub_marja]
    return rows


def preturi_sku(sku, an=None):
    if an is None:
        an = current_year()
    rows = query("""
        SELECT p.*, cl.*, pv.pret_vanzare_ron,
               rs.curs_ron AS curs_default,
               (SELECT cod FROM v_sku_cod WHERE v_sku_cod.sku = p.sku) AS cod_produs
        FROM produse p
        LEFT JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
        LEFT JOIN preturi_vanzare pv ON pv.sku = p.sku
                  AND pv.an = :an AND pv.cod_client IS NULL
        LEFT JOIN rate_schimb rs ON rs.an = :an AND rs.moneda = cl.moneda
        WHERE p.sku = :sku
    """, {"sku": sku, "an": an})
    return rows[0] if rows else None


def preturi_client_sku(sku, an=None):
    """All client-specific prices for a SKU."""
    if an is None:
        an = current_year()
    return query("""
        SELECT pv.*, t.client
        FROM preturi_vanzare pv
        LEFT JOIN (SELECT DISTINCT cod_client, client FROM tranzactii) t
            ON t.cod_client = pv.cod_client
        WHERE pv.sku = :sku AND pv.an = :an
        ORDER BY pv.cod_client NULLS FIRST
    """, {"sku": sku, "an": an})


def preturi_update_landing(sku, an, pret_valuta, moneda, curs, transport_pct,
                           taxa_vamala_pct, alte_costuri):
    db = get_db()
    pret_ron = pret_valuta * curs
    taxa_ron = pret_ron * taxa_vamala_pct / 100
    landing  = round(pret_ron * (1 + transport_pct / 100) + taxa_ron + alte_costuri, 4)
    db.execute("""
        INSERT OR REPLACE INTO costuri_landing
            (an, sku, moneda, pret_achizitie_valuta, curs_ron, pret_achizitie_ron,
             transport_pct, taxa_vamala_pct, alte_costuri_ron, landing_cost_ron)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (an, sku, moneda, pret_valuta, curs, round(pret_ron, 4),
          transport_pct, taxa_vamala_pct, alte_costuri, landing))
    db.commit()
    db.close()
    return landing


def preturi_update_vanzare(sku, an, pret, cod_client=None):
    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO preturi_vanzare
            (an, sku, cod_client, pret_vanzare_ron, activ)
        VALUES (?,?,?,?,1)
    """, (an, sku, cod_client, pret))
    db.commit()
    db.close()


def preturi_update_produs(sku, hs_code, taxa_mfn, taxa_aplicata, tva_pct):
    db = get_db()
    db.execute("""
        UPDATE produse SET hs_code=?, taxa_vamala_mfn_pct=?, taxa_vamala_pct=?, tva_pct=?
        WHERE sku=?
    """, (hs_code, taxa_mfn, taxa_aplicata, tva_pct, sku))
    db.commit()
    db.close()


def rate_schimb_list(an=None):
    if an is None:
        an = current_year()
    return query("SELECT * FROM rate_schimb WHERE an=:an ORDER BY moneda", {"an": an})


def rate_schimb_update(an, moneda, curs):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO rate_schimb (an, moneda, curs_ron) VALUES (?,?,?)",
               (an, moneda, curs))
    db.commit()
    db.close()


def furnizori_list():
    return query("SELECT DISTINCT furnizor FROM produse WHERE activ=1 ORDER BY furnizor")


# ── Condiții comerciale ──────────────────────────────────────────────────────

def conditii_list(an=None, cod_client=None, furnizor=None):
    filters, params = [], {}
    if an:
        filters.append("c.an = :an")
        params['an'] = an
    if cod_client:
        filters.append("c.cod_client = :cod_client")
        params['cod_client'] = cod_client
    if furnizor:
        filters.append("c.furnizor = :furnizor")
        params['furnizor'] = furnizor
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return query(f"""
        SELECT c.id, c.an, c.cod_client,
               t.client,
               c.furnizor, c.tip_valoare, c.periodicitate,
               c.valoare, c.descriere, c.data_creare
        FROM conditii_comerciale c
        LEFT JOIN (
            SELECT DISTINCT cod_client, client FROM tranzactii
        ) t ON t.cod_client = c.cod_client
        {where}
        ORDER BY c.an DESC, t.client, c.furnizor
    """, params)


def conditii_get(id):
    rows = query("SELECT * FROM conditii_comerciale WHERE id = :id", {"id": id})
    return rows[0] if rows else None


def conditii_create(an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere):
    import datetime
    db = get_db()
    db.execute("""
        INSERT INTO conditii_comerciale
            (an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere, data_creare)
        VALUES (?,?,?,?,?,?,?,?)
    """, (an, cod_client or None, furnizor or None, tip_valoare, periodicitate,
          valoare, descriere or None, datetime.date.today().isoformat()))
    db.commit()


def conditii_update(id, an, cod_client, furnizor, tip_valoare, periodicitate, valoare, descriere):
    db = get_db()
    db.execute("""
        UPDATE conditii_comerciale
        SET an=?, cod_client=?, furnizor=?, tip_valoare=?, periodicitate=?, valoare=?, descriere=?
        WHERE id=?
    """, (an, cod_client or None, furnizor or None, tip_valoare, periodicitate,
          valoare, descriere or None, id))
    db.commit()


def conditii_delete(id):
    db = get_db()
    db.execute("DELETE FROM conditii_comerciale WHERE id=?", (id,))
    db.commit()


def termene_list(an=None, cod_client=None):
    filters, params = [], {}
    if an:
        filters.append("t.an = :an")
        params['an'] = an
    if cod_client:
        filters.append("t.cod_client = :cod_client")
        params['cod_client'] = cod_client
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return query(f"""
        SELECT t.id, t.an, t.cod_client, tr.client, t.zile_termen, t.observatii, t.data_creare
        FROM termene_plata t
        LEFT JOIN (SELECT DISTINCT cod_client, client FROM tranzactii) tr
            ON tr.cod_client = t.cod_client
        {where}
        ORDER BY t.an DESC, tr.client
    """, params)


def termene_create(an, cod_client, zile_termen, observatii):
    import datetime
    db = get_db()
    db.execute("""
        INSERT INTO termene_plata (an, cod_client, zile_termen, observatii, data_creare)
        VALUES (?,?,?,?,?)
    """, (an, cod_client, zile_termen, observatii or None, datetime.date.today().isoformat()))
    db.commit()


def termene_delete(id):
    db = get_db()
    db.execute("DELETE FROM termene_plata WHERE id=?", (id,))
    db.commit()


# ── Articol nou (creare manuala) ─────────────────────────────────────────────

def produs_create(d):
    """Insert a new product plus optional logistics/media/landing rows.

    d: dict with produse fields (sku required) and optional keys
    logistica (dict), poza_url (str), landing (dict with pret_valuta,
    moneda, curs, transport_pct, taxa_vamala_pct, alte_costuri, an).
    Returns an error string or None on success.
    """
    sku = (d.get('sku') or '').strip()
    if not sku:
        return 'SKU obligatoriu.'
    db = get_db()
    try:
        if db.execute("SELECT 1 FROM produse WHERE sku=?", (sku,)).fetchone():
            return f'SKU {sku} exista deja.'
        db.execute("""
            INSERT INTO produse (sku, descriere, furnizor, brand, categorie,
                gramaj, buc_cutie, ean, tva_pct, hs_code, taxa_vamala_mfn_pct,
                taxa_vamala_pct, origine, tara_origine, activ, gama, potential)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
        """, (sku, d.get('descriere'), d.get('furnizor'), d.get('brand'),
              d.get('categorie'), d.get('gramaj'), d.get('buc_cutie'),
              d.get('ean'), d.get('tva_pct', 0.09), d.get('hs_code'),
              d.get('taxa_vamala_mfn_pct', 0), d.get('taxa_vamala_pct', 0),
              d.get('origine', 'import_extraeu'), d.get('tara_origine'),
              d.get('gama') or d.get('furnizor'),
              1 if d.get('potential') else 0))
        log = d.get('logistica') or {}
        if any(v is not None for v in log.values()):
            db.execute("""
                INSERT INTO produse_logistica (sku, unit_net_kg, unit_gross_kg,
                    bax_l_mm, bax_w_mm, bax_h_mm, bax_gross_kg, bax_cbm,
                    buc_bax, bax_palet, valabilitate_luni, moq, sursa)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manual')
            """, (sku, log.get('unit_net_kg'), log.get('unit_gross_kg'),
                  log.get('bax_l_mm'), log.get('bax_w_mm'), log.get('bax_h_mm'),
                  log.get('bax_gross_kg'), log.get('bax_cbm'),
                  log.get('buc_bax'), log.get('bax_palet'),
                  log.get('valabilitate_luni'), log.get('moq')))
        if d.get('poza_url'):
            db.execute("INSERT INTO produse_media (sku, url_sursa, principala)"
                       " VALUES (?,?,1)", (sku, d['poza_url'].strip()))
        db.commit()
    finally:
        db.close()
    lnd = d.get('landing') or {}
    if lnd.get('pret_valuta') and lnd.get('curs'):
        preturi_update_landing(
            sku, lnd['an'], lnd['pret_valuta'], lnd.get('moneda', 'EUR'),
            lnd['curs'], lnd.get('transport_pct', 10),
            lnd.get('taxa_vamala_pct', 0), lnd.get('alte_costuri', 0))
    return None


def produse_atribute_distincte():
    """Distinct furnizor/brand/categorie/gama values for form datalists."""
    out = {}
    for col in ('furnizor', 'brand', 'categorie', 'gama'):
        out[col] = [r[col] for r in query(
            f"SELECT DISTINCT {col} FROM produse WHERE {col} IS NOT NULL "
            f"AND {col} != '' ORDER BY {col}")]
    return out


# ── Actualizare preturi furnizor existent (F5) ──────────────────────────────

def furnizor_preturi_curente(furnizor, an):
    """Current purchase prices + landing params + last order price per SKU
    of a supplier - the base for the price-update diff."""
    return query("""
        SELECT p.sku, p.descriere,
               cl.moneda, cl.pret_achizitie_valuta, cl.curs_ron,
               cl.transport_pct, cl.taxa_vamala_pct, cl.alte_costuri_ron,
               cl.landing_cost_ron,
               (SELECT cfl.pret_valuta FROM comenzi_furnizori_linii cfl
                JOIN comenzi_furnizori cf ON cf.id = cfl.comanda_id
                WHERE cfl.sku = p.sku
                ORDER BY cf.data_comanda DESC, cfl.id DESC LIMIT 1)
                   AS pret_ultima_comanda,
               (SELECT cfl.cod_furnizor FROM comenzi_furnizori_linii cfl
                WHERE cfl.sku = p.sku AND cfl.cod_furnizor IS NOT NULL
                ORDER BY cfl.id DESC LIMIT 1) AS cod_furnizor
        FROM produse p
        LEFT JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
        WHERE p.activ = 1 AND (p.furnizor = :f OR p.gama = :f)
    """, {"f": furnizor, "an": an})


# ── Clienti prospect (oferte pentru clienti inexistenti in ERP) ─────────────

def clienti_prospecti_list():
    """clienti_pricing rows that do not exist in tranzactii (prospects)."""
    return query("""
        SELECT cp.cod_client, cp.nume_client
        FROM clienti_pricing cp
        WHERE cp.activ = 1 AND NOT EXISTS (
            SELECT 1 FROM tranzactii t WHERE t.cod_client = cp.cod_client)
        ORDER BY cp.nume_client
    """)


def client_prospect_create(nume):
    """Register a prospect client; returns its generated code."""
    nume = (nume or '').strip()
    if not nume:
        return None, 'Numele clientului este obligatoriu.'
    db = get_db()
    try:
        row = db.execute(
            "SELECT cod_client FROM clienti_pricing WHERE upper(nume_client)=upper(?)",
            (nume,)).fetchone()
        if row:
            return row[0], None
        n = db.execute("SELECT COUNT(*) FROM clienti_pricing "
                       "WHERE cod_client LIKE 'PROSPECT-%'").fetchone()[0]
        cod = f'PROSPECT-{n + 1}'
        db.execute("INSERT INTO clienti_pricing (cod_client, nume_client,"
                   " template_listare) VALUES (?, ?, 'generic')", (cod, nume))
        db.commit()
        return cod, None
    finally:
        db.close()


# ── Poze articole ────────────────────────────────────────────────────────────

def produs_poza(sku):
    rows = query("SELECT * FROM produse_media WHERE sku = :sku AND principala = 1"
                 " ORDER BY id DESC LIMIT 1", {"sku": sku})
    return rows[0] if rows else None


def produs_poza_set(sku, path=None, url_sursa=None):
    db = get_db()
    db.execute("UPDATE produse_media SET principala = 0 WHERE sku = ?", (sku,))
    db.execute("INSERT INTO produse_media (sku, path, url_sursa, principala)"
               " VALUES (?,?,?,1)", (sku, path, url_sursa))
    db.commit()
    db.close()


# ── Simulator + propuneri de pret (F2) ───────────────────────────────────────

def simulator_articole(an, cod_client):
    """Articles with a landing cost, plus the client's and standard price."""
    return query("""
        SELECT p.sku, p.descriere, p.furnizor, p.categorie, p.gama,
               p.potential,
               cl.landing_cost_ron,
               pvc.pret_vanzare_ron AS pret_client,
               pvs.pret_vanzare_ron AS pret_standard
        FROM produse p
        JOIN costuri_landing cl ON cl.sku = p.sku AND cl.an = :an
             AND cl.landing_cost_ron IS NOT NULL
        LEFT JOIN preturi_vanzare pvc ON pvc.sku = p.sku AND pvc.an = :an
             AND pvc.cod_client = :cod_client AND pvc.activ = 1
        LEFT JOIN preturi_vanzare pvs ON pvs.sku = p.sku AND pvs.an = :an
             AND pvs.cod_client IS NULL AND pvs.activ = 1
        WHERE p.activ = 1
        ORDER BY p.furnizor, p.sku
    """, {"an": an, "cod_client": cod_client})


def propuneri_list(an=None, cod_client=None):
    filters, params = ["1=1"], {}
    if an:
        filters.append("pp.an = :an")
        params['an'] = an
    if cod_client:
        filters.append("pp.cod_client = :cod_client")
        params['cod_client'] = cod_client
    return query(f"""
        SELECT pp.*, COALESCE(t.client, cp.nume_client) AS client,
               COUNT(li.id) AS nr_linii,
               SUM(CASE WHEN li.verdict = 'aprobare_director' THEN 1 ELSE 0 END)
                   AS nr_sub_aprobare
        FROM propuneri_pret pp
        LEFT JOIN (SELECT DISTINCT cod_client, client FROM tranzactii) t
            ON t.cod_client = pp.cod_client
        LEFT JOIN clienti_pricing cp ON cp.cod_client = pp.cod_client
        LEFT JOIN propuneri_pret_linii li ON li.propunere_id = pp.id
        WHERE {' AND '.join(filters)}
        GROUP BY pp.id
        ORDER BY pp.creat_la DESC
    """, params)


def propunere_get(id):
    rows = query("SELECT * FROM propuneri_pret WHERE id = :id", {"id": id})
    if not rows:
        return None
    linii = query("""
        SELECT li.*, p.descriere, p.furnizor
        FROM propuneri_pret_linii li
        LEFT JOIN produse p ON p.sku = li.sku
        WHERE li.propunere_id = :id ORDER BY p.furnizor, li.sku
    """, {"id": id})
    return {"propunere": rows[0], "linii": linii}


def propunere_create(an, cod_client, titlu, linii):
    """linii: list of dicts with sku, pret_actual, pret_propus, landing_ron,
    cond_pct, marja_neta_pct, verdict (computed by the caller via the
    pricing engine). Returns the new proposal id."""
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO propuneri_pret (an, cod_client, titlu) VALUES (?,?,?)",
            (an, cod_client, titlu or None))
        pid = cur.lastrowid
        db.executemany("""
            INSERT INTO propuneri_pret_linii (propunere_id, sku, pret_actual,
                pret_propus, landing_ron, cond_pct, marja_neta_pct, verdict)
            VALUES (?,?,?,?,?,?,?,?)
        """, [(pid, li['sku'], li.get('pret_actual'), li['pret_propus'],
               li.get('landing_ron'), li.get('cond_pct'),
               li.get('marja_neta_pct'), li.get('verdict')) for li in linii])
        db.commit()
        return pid
    finally:
        db.close()


def propunere_linii_export(id):
    """Proposal lines enriched with product, logistics and the client's
    internal article codes - everything the client file templates need."""
    rows = query("SELECT * FROM propuneri_pret WHERE id = :id", {"id": id})
    if not rows:
        return None
    prop = rows[0]
    linii = query("""
        SELECT li.sku, li.pret_actual, li.pret_propus, li.marja_neta_pct,
               li.verdict,
               p.descriere, p.gramaj, p.ean, p.tva_pct, p.buc_cutie,
               p.hs_code, p.tara_origine, p.brand,
               pl.buc_bax, pl.bax_palet, pl.unit_net_kg, pl.unit_gross_kg,
               pl.bax_l_mm, pl.bax_w_mm, pl.bax_h_mm, pl.bax_gross_kg,
               pl.bax_cbm, pl.valabilitate_luni,
               cca.cod_intern, cca.cod_intern2,
               pm.path AS poza_path, pm.url_sursa AS poza_url
        FROM propuneri_pret_linii li
        LEFT JOIN produse p  ON p.sku = li.sku
        LEFT JOIN produse_logistica pl ON pl.sku = li.sku
        LEFT JOIN coduri_client_articol cca ON cca.sku = li.sku
             AND cca.cod_client = :cod_client
        LEFT JOIN produse_media pm ON pm.id = (
            SELECT id FROM produse_media
            WHERE sku = li.sku AND principala = 1 LIMIT 1)
        WHERE li.propunere_id = :id
        ORDER BY p.furnizor, li.sku
    """, {"id": id, "cod_client": prop['cod_client']})
    client = query("""
        SELECT COALESCE(
            (SELECT client FROM tranzactii WHERE cod_client = :c LIMIT 1),
            (SELECT nume_client FROM clienti_pricing WHERE cod_client = :c)
        ) AS client
    """, {"c": prop['cod_client']})
    client = [c for c in client if c['client']]
    template = query("""
        SELECT template_listare FROM clienti_pricing WHERE cod_client = :c
    """, {"c": prop['cod_client']})
    return {
        "propunere": prop,
        "linii": linii,
        "nume_client": client[0]['client'] if client else prop['cod_client'],
        "template": template[0]['template_listare'] if template else None,
    }


def propunere_delete(id):
    db = get_db()
    db.execute("DELETE FROM propuneri_pret WHERE id=?", (id,))
    db.commit()
    db.close()


def marja_ajustata(an):
    """Adjusted margin per client/brand after applying commercial conditions."""
    return query("""
    WITH
    -- Base: annual sales + margin per client + brand
    base AS (
        SELECT cod_client, client, furnizor,
               ROUND(SUM(val_neta),2)    AS val_neta,
               ROUND(SUM(marja_bruta),2) AS marja_bruta
        FROM tranzactii WHERE an = :an
        GROUP BY cod_client, client, furnizor
    ),
    -- All applicable conditions for each client+brand (priority: specific > general)
    cond AS (
        SELECT
            b.cod_client, b.furnizor,
            -- Pick most specific condition: client+brand > client+all > all+brand > all+all
            MAX(CASE WHEN c.cod_client IS NOT NULL AND c.furnizor IS NOT NULL THEN 4
                     WHEN c.cod_client IS NOT NULL AND c.furnizor IS NULL     THEN 3
                     WHEN c.cod_client IS NULL     AND c.furnizor IS NOT NULL THEN 2
                     ELSE 1 END) AS priority,
            SUM(CASE
                WHEN c.tip_valoare='pct' AND c.periodicitate='lunar'
                    THEN b.val_neta * c.valoare / 100
                WHEN c.tip_valoare='pct' AND c.periodicitate='anual'
                    THEN b.val_neta * c.valoare / 100
                WHEN c.tip_valoare='suma_fixa'
                    THEN c.valoare
                ELSE 0 END) AS cost_conditii
        FROM base b
        JOIN conditii_comerciale c ON c.an = :an
            AND (c.cod_client = b.cod_client OR c.cod_client IS NULL)
            AND (c.furnizor   = b.furnizor   OR c.furnizor   IS NULL)
        GROUP BY b.cod_client, b.furnizor
    )
    SELECT b.cod_client, b.client, b.furnizor,
           b.val_neta, b.marja_bruta,
           ROUND(COALESCE(c.cost_conditii, 0), 2)                   AS cost_conditii,
           ROUND(b.marja_bruta - COALESCE(c.cost_conditii, 0), 2)   AS marja_ajustata,
           ROUND((b.marja_bruta - COALESCE(c.cost_conditii,0))
                 / NULLIF(b.val_neta,0) * 100, 2)                   AS marja_ajustata_pct
    FROM base b
    LEFT JOIN cond c ON c.cod_client = b.cod_client AND c.furnizor = b.furnizor
    ORDER BY b.client, b.furnizor
    """, {"an": an})


# ── Forecast stoc ────────────────────────────────────────────────────────────

