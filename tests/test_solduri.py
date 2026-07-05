import os
import importlib.util
import datetime as _dt
import pytest

import queries  # conftest puts app/ on sys.path
import db as _db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "docs_input", "rapoarte", "neinc 30 06.xls")


def _etl():
    path = os.path.join(ROOT, "etl", "import_solduri_neincasate.py")
    spec = importlib.util.spec_from_file_location("_solduri_etl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ETL parse ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="sample xls not present")
def test_parse_sample():
    rows = _etl().parse_solduri_xls(SAMPLE)
    assert len(rows) > 1000
    r = rows[0]
    assert set(r) >= {"nrdl", "datadl", "term_pl_cl", "sumdeincas",
                      "numecli", "codcli", "numeag", "factout", "vtdl"}
    assert r["datadl"] is None or len(r["datadl"]) == 10
    assert any((x["sumdeincas"] or 0) < 0 for x in rows)  # advances/credit notes
    assert all(isinstance(x["term_pl_cl"], int)
               for x in rows if x["term_pl_cl"] is not None)


# ── seed helper (term=0 → scadenta == datadl == today+offset) ────────────────

def _seed(rows):
    """rows: list of (offset_days_to_due, amount)."""
    conn = _db.get_db()
    conn.execute("DELETE FROM solduri_neincasate")
    today = _dt.date.today()
    for i, (d, amt) in enumerate(rows):
        datadl = (today + _dt.timedelta(days=d)).isoformat()
        conn.execute(
            "INSERT INTO solduri_neincasate "
            "(data_raport, datadl, term_pl_cl, numecli, codcli, numeag, factout, sumdeincas) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (today.isoformat(), datadl, 0, f"CLI{i % 3}", f"C{i % 3}",
             f"AG{i % 2}", f"F{i}", amt),
        )
    conn.commit()
    conn.close()


# ── aging KPI ────────────────────────────────────────────────────────────────

def test_kpi_buckets():
    _seed([(0, 100), (5, 100), (20, 100), (45, 100), (100, 100),
           (-3, 100), (-15, 100), (-50, 100), (-200, 100), (-10, -40)])
    k = queries.solduri_kpi()
    assert round(k["nesc7"]) == 200
    assert round(k["nesc30"]) == 300
    assert round(k["nesc60"]) == 400
    assert round(k["scad7"]) == 100
    assert round(k["scad30"]) == 160
    assert round(k["scad60"]) == 260
    assert round(k["total_scadent"]) == 360
    assert round(k["catchall"]) == 200
    assert round(k["total_piata"]) == 860
    # reconciliation identity
    assert round(k["nesc60"] + k["scad60"] + k["catchall"], 2) == round(k["total_piata"], 2)


def test_meta():
    _seed([(0, 100), (-3, 50)])
    m = queries.solduri_meta()
    assert m["nr_randuri"] == 2
    assert m["data_raport"] == _dt.date.today().isoformat()


# ── table views ──────────────────────────────────────────────────────────────

def test_by_client_shapes_and_filter():
    _seed([(0, 100), (-3, 50), (-200, 70)])
    rows = queries.solduri_by_client()
    assert rows and set(rows[0]) >= {
        "numecli", "codcli", "numeag", "total", "nesc7", "scad7",
        "plafon", "zile_restanta_max", "depasit_plafon"}
    assert round(sum(r["total"] for r in rows), 2) == 220.0
    r7 = queries.solduri_by_client(bucket="scad7")
    assert round(sum(r["total"] for r in r7), 2) == 50.0


def test_by_agent_and_invoice():
    _seed([(0, 100), (-3, 50)])
    ag = queries.solduri_by_agent()
    assert ag and "nr_clienti" in ag[0] and "total" in ag[0]
    inv = queries.solduri_by_invoice(bucket="scad7")
    assert len(inv) == 1
    assert inv[0]["zile"] == -3
    assert inv[0]["bucket_label"]


def test_client_header_and_invoices():
    # C0 gets rows i=0 (due today, 100) and i=3 (40d overdue, 30)
    _seed([(0, 100), (-3, 50), (-10, 70), (-40, 30)])
    h = queries.solduri_client_header("C0")
    assert h["numecli"] == "CLI0"
    assert round(h["total"], 2) == 130.0
    assert round(h["total_scadent"], 2) == 30.0
    assert h["zile_restanta_max"] == 40
    assert h["nr_documente"] == 2
    inv = queries.solduri_by_invoice(codcli="C0")
    assert len(inv) == 2
    assert all(r["codcli"] == "C0" for r in inv)
    # missing client -> aggregate row with zero documents
    miss = queries.solduri_client_header("NOPE")
    assert not miss or not miss["nr_documente"]


def test_agents_list():
    _seed([(0, 100), (-3, 50)])
    assert set(queries.solduri_agents()) == {"AG0", "AG1"}


# ── route smoke ──────────────────────────────────────────────────────────────

def test_route_renders(client):
    _seed([(0, 100), (-3, 50)])
    assert client.get('/solduri-neincasate').status_code == 200
    assert client.get('/solduri-neincasate?view=agent').status_code == 200
    assert client.get('/solduri-neincasate?view=invoice&bucket=scad7').status_code == 200
    assert client.get('/solduri-neincasate/export/excel').status_code == 200


def test_client_detail_route(client):
    _seed([(0, 100), (-3, 50)])
    assert client.get('/solduri-neincasate/client/C0').status_code == 200
    assert client.get('/solduri-neincasate/client/NOPE').status_code == 404
    assert client.get(
        '/solduri-neincasate/export/excel?view=invoice&codcli=C0'
    ).status_code == 200
