from db import query, query_one, get_db


def termene_aprovizionare_list():
    return query("SELECT * FROM termene_aprovizionare ORDER BY furnizor")


def termene_partial_update(furnizor: str, zile: int, sezon_craciun: int = 0, observatii: str = None):
    """Actualizează doar zile_livrare, sezon_craciun, observatii — tab Termene din forecast."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO termene_aprovizionare (furnizor, zile_livrare, sezon_craciun, observatii)
            VALUES (:f, :z, :s, :o)
            ON CONFLICT(furnizor) DO UPDATE SET
                zile_livrare  = excluded.zile_livrare,
                sezon_craciun = excluded.sezon_craciun,
                observatii    = excluded.observatii
        """, {'f': furnizor, 'z': zile, 's': sezon_craciun, 'o': observatii})
        conn.commit()
    finally:
        conn.close()


# ── Comenzi furnizori ─────────────────────────────────────────────────────────

def comenzi_list(furnizor=None, status=None):
    filters, params = [], {}
    if furnizor:
        filters.append("c.furnizor = :furnizor")
        params['furnizor'] = furnizor
    if status:
        filters.append("c.status = :status")
        params['status'] = status
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    return query(f"""
        SELECT c.id, c.nr_comanda, c.furnizor, c.data_comanda, c.status,
               c.data_estimata_livrare, c.data_confirmare_furnizor, c.observatii,
               c.created_at, c.updated_at,
               COUNT(l.id)  AS nr_linii,
               SUM(COALESCE(l.cantitate_confirmata, l.cantitate_comandata)) AS total_qty,
               SUM(COALESCE(l.cantitate_ro, 0))     AS total_ro,
               SUM(COALESCE(l.cantitate_export, 0)) AS total_export
        FROM comenzi_furnizori c
        LEFT JOIN comenzi_furnizori_linii l ON l.comanda_id = c.id
        {where}
        GROUP BY c.id
        ORDER BY c.data_comanda DESC, c.id DESC
    """, params)


def comanda_get(comanda_id: int) -> dict | None:
    h = query_one("SELECT * FROM comenzi_furnizori WHERE id = :id", {'id': comanda_id})
    if not h:
        return None
    lines = query("""
        SELECT l.id, l.sku, l.cantitate_sugerat, l.cantitate_comandata,
               l.cantitate_ro, l.cantitate_export,
               l.cantitate_confirmata, l.pret_valuta, l.moneda, l.observatii,
               l.cod_furnizor, l.units_per_carton, l.cantitate_baxuri,
               l.gross_kg, l.net_kg, l.cbm, l.total_valuta,
               COALESCE(l.descriere, p.descriere, l.sku) AS descriere,
               COALESCE(l.cod_furnizor, (SELECT cod FROM v_sku_cod WHERE v_sku_cod.sku = l.sku)) AS cod_produs
        FROM comenzi_furnizori_linii l
        LEFT JOIN produse p ON p.sku = l.sku
        WHERE l.comanda_id = :id ORDER BY l.sku
    """, {'id': comanda_id})
    return {'header': dict(h), 'lines': lines}


def comanda_create(furnizor: str, nr_comanda: str = None, observatii: str = None) -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO comenzi_furnizori (furnizor, nr_comanda, observatii) VALUES (:f, :nr, :obs)",
            {'f': furnizor, 'nr': nr_comanda, 'obs': observatii}
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def comanda_update(comanda_id: int, **kwargs):
    allowed = {'nr_comanda', 'status', 'data_estimata_livrare',
               'data_confirmare_furnizor', 'observatii'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    sets = ', '.join(f"{k} = :{k}" for k in fields)
    fields['id'] = comanda_id
    import datetime as _dt
    fields['now'] = _dt.datetime.now().isoformat()
    conn = get_db()
    try:
        conn.execute(
            f"UPDATE comenzi_furnizori SET {sets}, updated_at = :now WHERE id = :id",
            fields
        )
        conn.commit()
    finally:
        conn.close()


def comanda_delete(comanda_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM comenzi_furnizori WHERE id = :id", {'id': comanda_id})
        conn.commit()
    finally:
        conn.close()


def comanda_line_upsert(comanda_id: int, sku: str, cantitate_comandata: int,
                         cantitate_sugerat: int = 0, pret_valuta: float = None,
                         moneda: str = 'EUR', observatii: str = None,
                         cantitate_ro: int = 0, cantitate_export: int = 0,
                         cod_furnizor: str = None) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM comenzi_furnizori_linii WHERE comanda_id=:cid AND sku=:sku",
            {'cid': comanda_id, 'sku': sku}
        ).fetchone()
        if row:
            conn.execute("""
                UPDATE comenzi_furnizori_linii
                SET cantitate_comandata=:qty, cantitate_sugerat=:sq,
                    cantitate_ro=:qro, cantitate_export=:qexp,
                    pret_valuta=:pv, moneda=:m, observatii=:obs,
                    cod_furnizor=COALESCE(:cf, cod_furnizor)
                WHERE id=:id
            """, {'qty': cantitate_comandata, 'sq': cantitate_sugerat,
                  'qro': cantitate_ro, 'qexp': cantitate_export,
                  'pv': pret_valuta, 'm': moneda, 'obs': observatii,
                  'cf': cod_furnizor, 'id': row[0]})
            lid = row[0]
        else:
            cur = conn.execute("""
                INSERT INTO comenzi_furnizori_linii
                    (comanda_id, sku, cantitate_sugerat, cantitate_comandata,
                     cantitate_ro, cantitate_export, pret_valuta, moneda, observatii, cod_furnizor)
                VALUES (:cid, :sku, :sq, :qty, :qro, :qexp, :pv, :m, :obs, :cf)
            """, {'cid': comanda_id, 'sku': sku, 'sq': cantitate_sugerat,
                  'qty': cantitate_comandata, 'qro': cantitate_ro, 'qexp': cantitate_export,
                  'pv': pret_valuta, 'm': moneda, 'obs': observatii, 'cf': cod_furnizor})
            lid = cur.lastrowid
        conn.commit()
        return lid
    finally:
        conn.close()


def comanda_line_update(line_id: int, **kwargs):
    allowed = {'cantitate_comandata', 'cantitate_confirmata', 'cantitate_ro', 'cantitate_export',
               'pret_valuta', 'moneda', 'observatii', 'cod_furnizor'}
    # Filter out None — `cantitate_comandata` has NOT NULL constraint and the
    # JS often sends only the field user actually edited.
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    sets = ', '.join(f"{k} = :{k}" for k in fields)
    fields['id'] = line_id
    conn = get_db()
    try:
        conn.execute(f"UPDATE comenzi_furnizori_linii SET {sets} WHERE id = :id", fields)
        conn.commit()
    finally:
        conn.close()


def comanda_line_delete(line_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM comenzi_furnizori_linii WHERE id = :id", {'id': line_id})
        conn.commit()
    finally:
        conn.close()



def termene_aprovizionare_upsert(furnizor: str, zile_min: int, zile_max: int, moneda: str,
                                 tip_produs: str, sezon_craciun: int, observatii: str = None):
    db = get_db()
    try:
        db.execute("""
            INSERT INTO termene_aprovizionare
                (furnizor, zile_livrare_min, zile_livrare, moneda, tip_produs, sezon_craciun, observatii)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(furnizor) DO UPDATE SET
                zile_livrare_min=excluded.zile_livrare_min,
                zile_livrare=excluded.zile_livrare,
                moneda=excluded.moneda,
                tip_produs=excluded.tip_produs,
                sezon_craciun=excluded.sezon_craciun,
                observatii=excluded.observatii
        """, (furnizor, zile_min, zile_max, moneda, tip_produs, sezon_craciun, observatii))
        db.commit()
    finally:
        db.close()

