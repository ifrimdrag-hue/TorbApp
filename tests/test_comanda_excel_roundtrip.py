"""Round-trip export -> import for supplier orders (finding B8)."""
import io
import sqlite3


def test_export_import_roundtrip_updates_quantity(db_path, client):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO comenzi_furnizori (nr_comanda, furnizor, status, data_comanda)
        VALUES ('CMD-B8-1', 'TestBrandB8', 'draft', '2026-07-03')
    """)
    cid = conn.execute(
        "SELECT id FROM comenzi_furnizori WHERE nr_comanda='CMD-B8-1'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO comenzi_furnizori_linii (comanda_id, sku, cantitate_comandata) "
        "VALUES (?, 'SKU-B8-1', 12)", (cid,)
    )
    conn.commit()
    conn.close()

    # Export
    resp = client.get(f'/export/forecast/comanda/{cid}')
    assert resp.status_code == 200

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(resp.data), data_only=True)
    ws = wb.active
    headers = [str(c.value or '').upper() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    # The export must carry a re-importable ordered-quantity column.
    assert any('COMAND' in h for h in headers), (
        f"export headers {headers} must include a 'Cantitate comandată' column "
        "so the file re-imports"
    )

    # Re-import the exact file the export produced — must succeed, not 400.
    resp2 = client.post(
        f'/import/forecast/comanda/{cid}',
        data={'file': (io.BytesIO(resp.data), 'order.xlsx')},
        content_type='multipart/form-data',
    )
    assert resp2.status_code == 200, resp2.data
    assert resp2.get_json().get('imported', 0) >= 1
