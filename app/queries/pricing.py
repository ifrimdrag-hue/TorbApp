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

