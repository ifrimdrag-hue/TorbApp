from db import query, get_db


def get_export_hu_codes() -> set:
    """Set de cod_client care mapează la bucketul HU (gestiune separată)."""
    rows = query("""
        SELECT ce.cod_client
        FROM clienti_export ce
        JOIN tari_export te ON ce.tara_id = te.id
        WHERE ce.activ = 1 AND te.piata = 'HU'
    """)
    return {r['cod_client'] for r in rows}


def monthly_sales_ro_hu(furnizor: str | None) -> dict:
    """Vânzări medii lunare per SKU, split RO/HU strict separate.
    Returnează {sku: {'ro': {1..12: qty}, 'hu': {1..12: qty},
                      'ro_prev': {1..12: qty}, 'hu_prev': {1..12: qty},
                      'cod_produs': str}}
    """
    from datetime import date
    from db import _conn, has_app_context
    hu_codes = get_export_hu_codes()
    hu_list  = list(hu_codes) if hu_codes else ['~~EMPTY~~']

    hu_ph = ','.join(['?' for _ in hu_list])

    furn_where = "AND furnizor = ?" if furnizor else ""
    sql = f"""
        SELECT
            sku, cod_produs, luna, an,
            SUM(CASE WHEN cod_client NOT IN ({hu_ph}) THEN cantitate ELSE 0 END) AS qty_ro,
            SUM(CASE WHEN cod_client IN     ({hu_ph}) THEN cantitate ELSE 0 END) AS qty_hu
        FROM tranzactii
        WHERE an >= ?
          AND cantitate > 0
          {furn_where}
        GROUP BY sku, cod_produs, luna, an
        ORDER BY sku, an, luna
    """

    today = date.today()
    an_start = today.year - 2
    params = hu_list + hu_list + [an_start]
    if furnizor:
        params.append(furnizor)

    conn = _conn()
    transient = not has_app_context()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        if transient:
            conn.close()

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {
                'cod_produs': r['cod_produs'],
                'ro': {}, 'hu': {}, 'ro_prev': {}, 'hu_prev': {}
            }
        m = r['luna']
        if r['an'] == today.year:
            result[sku]['ro'][m] = result[sku]['ro'].get(m, 0) + r['qty_ro']
            result[sku]['hu'][m] = result[sku]['hu'].get(m, 0) + r['qty_hu']
        else:
            result[sku]['ro_prev'][m] = result[sku]['ro_prev'].get(m, 0) + r['qty_ro']
            result[sku]['hu_prev'][m] = result[sku]['hu_prev'].get(m, 0) + r['qty_hu']
    return result


def stoc_ro_hu(furnizor: str = None) -> dict:
    """Stoc fizic per SKU per piață (RO/HU) din ultimul snapshot.
    Returnează {sku: {'ro': qty, 'hu': qty, 'val_ro': val, 'val_hu': val,
                      'cod_produs': str, 'gama': str, 'furnizor': str,
                      'data_intrare_min': str}}
    """
    where = "AND furnizor = :furnizor" if furnizor else ""
    rows = query(f"""
        SELECT sku, cod_produs, gama, furnizor,
               COALESCE(piata,'RO') AS piata,
               SUM(cantitate) AS qty,
               SUM(cantitate * pret_achizitie) AS val,
               MIN(data_intrare) AS data_intrare_min
        FROM stoc
        WHERE data_snapshot = (SELECT MAX(data_snapshot) FROM stoc)
          {where}
        GROUP BY sku, cod_produs, gama, furnizor, piata
    """, {'furnizor': furnizor} if furnizor else {})

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {
                'cod_produs': r['cod_produs'], 'gama': r['gama'],
                'furnizor': r['furnizor'], 'descriere': '',
                'ro': 0.0, 'hu': 0.0, 'val_ro': 0.0, 'val_hu': 0.0,
                'data_intrare_min': r['data_intrare_min'],
            }
        if r['piata'] == 'HU':
            result[sku]['hu']     += r['qty'] or 0
            result[sku]['val_hu'] += r['val'] or 0
        else:
            result[sku]['ro']     += r['qty'] or 0
            result[sku]['val_ro'] += r['val'] or 0
    return result


def in_transit_ro_hu(furnizor: str) -> dict:
    """Cantitate în tranzit per SKU per piată din comenzi active.
    Status active: 'confirmata', 'in_tranzit'.
    Returnează {sku: {'ro': qty, 'hu': qty, 'comenzi': [...]}}
    """
    rows = query("""
        SELECT
            l.sku,
            cf.nr_comanda, cf.data_comanda, cf.status,
            cf.data_estimata_livrare AS eta,
            COALESCE(l.cantitate_confirmata, l.cantitate_comandata, 0) AS qty_total,
            COALESCE(l.cantitate_ro, 0)     AS qty_ro,
            COALESCE(l.cantitate_export, 0) AS qty_hu
        FROM comenzi_furnizori_linii l
        JOIN comenzi_furnizori cf ON cf.id = l.comanda_id
        WHERE cf.furnizor = :furnizor
          AND cf.status IN ('confirmata','in_tranzit')
        ORDER BY cf.data_comanda
    """, {'furnizor': furnizor})

    result = {}
    for r in rows:
        sku = r['sku']
        if sku not in result:
            result[sku] = {'ro': 0, 'hu': 0, 'comenzi': []}
        result[sku]['ro'] += r['qty_ro']
        result[sku]['hu'] += r['qty_hu']
        result[sku]['comenzi'].append({
            'nr_comanda':   r['nr_comanda'],
            'data_comanda': r['data_comanda'],
            'eta':          r['eta'],
            'status':       r['status'],
            'qty_ro':       r['qty_ro'],
            'qty_hu':       r['qty_hu'],
        })
    return result


def expirare_list(furnizor: str = None, prag_luni: int = 6, tip_produs: str = None) -> list:
    """Articole cu data_intrare mai veche de prag_luni luni din stoc_expirare."""
    from datetime import date, timedelta
    data_limita = (date.today() - timedelta(days=prag_luni * 30)).isoformat()

    where_parts = ["data_intrare IS NOT NULL", "data_intrare <= :data_limita", "cantitate > 0"]
    params = {'data_limita': data_limita}
    if furnizor:
        where_parts.append("furnizor = :furnizor")
        params['furnizor'] = furnizor

    inner_where = " AND ".join(where_parts)

    outer_tip_filter = ""
    if tip_produs:
        outer_tip_filter = "WHERE tip_produs_calc = :tip"
        params['tip'] = tip_produs

    rows = query(f"""
        SELECT * FROM (
            SELECT
                se.sku, se.cod_produs, se.furnizor, se.gama,
                se.data_intrare, se.data_expirare, se.cantitate,
                COALESCE(se.pret_achizitie, 0) * se.cantitate AS valoare,
                CAST(julianday('now') - julianday(se.data_intrare) AS INTEGER) AS vechime_zile,
                CASE
                    WHEN se.furnizor IN ('Basilur','KingsLeaf','Tipson','Organsia','Celmar') THEN 'Ceai'
                    WHEN se.furnizor IN ('Toras','Delaviuda') THEN 'Ciocolata'
                    ELSE 'Altele'
                END AS tip_produs_calc
            FROM stoc_expirare se
            WHERE {inner_where}
        )
        {outer_tip_filter}
        ORDER BY data_intrare ASC
    """, params)
    return rows


def tari_export_list() -> list:
    return query("SELECT * FROM tari_export ORDER BY tara")


def tari_export_upsert(tara: str, piata: str, activ: int, observatii: str = None, id: int = None):
    db = get_db()
    try:
        if id is not None:
            db.execute(
                "UPDATE tari_export SET tara=?,piata=?,activ=?,observatii=? WHERE id=?",
                (tara, piata, activ, observatii, id)
            )
        else:
            db.execute(
                "INSERT INTO tari_export (tara,piata,activ,observatii) VALUES (?,?,?,?)",
                (tara, piata, activ, observatii)
            )
        db.commit()
    finally:
        db.close()


def tari_export_delete(id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM clienti_export WHERE tara_id=?", (id,))
        db.execute("DELETE FROM tari_export WHERE id=?", (id,))
        db.commit()
    finally:
        db.close()


def clienti_export_list() -> list:
    return query("""
        SELECT ce.*, te.tara, te.piata
        FROM clienti_export ce
        JOIN tari_export te ON ce.tara_id = te.id
        ORDER BY te.tara, ce.nume_client
    """)


def clienti_export_upsert(tara_id: int, cod_client: str, nume_client: str,
                           activ: int, observatii: str = None, id: int = None):
    db = get_db()
    try:
        if id is not None:
            db.execute(
                "UPDATE clienti_export SET tara_id=?,cod_client=?,nume_client=?,activ=?,observatii=? WHERE id=?",
                (tara_id, cod_client, nume_client, activ, observatii, id)
            )
        else:
            db.execute(
                "INSERT INTO clienti_export (tara_id,cod_client,nume_client,activ,observatii) VALUES (?,?,?,?,?)",
                (tara_id, cod_client, nume_client, activ, observatii)
            )
        db.commit()
    finally:
        db.close()


def clienti_export_toggle(id: int):
    db = get_db()
    try:
        db.execute("UPDATE clienti_export SET activ = 1 - activ WHERE id=?", (id,))
        db.commit()
    finally:
        db.close()


