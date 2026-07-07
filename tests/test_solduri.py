import os
import importlib.util
import datetime as _dt
import pytest

import queries  # conftest puts app/ on sys.path
import db as _db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "docs_input", "rapoarte", "neinc 30 06.xls")
SAMPLE_NEW = os.path.join(ROOT, "docs_input", "rapoarte", "neincasate.xls")


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


@pytest.mark.skipif(not os.path.exists(SAMPLE_NEW),
                    reason="new-format sample xls not present")
def test_parse_new_format():
    # newer export mislabels its codepage → must fall back to iso-8859-2
    rows = _etl().parse_solduri_xls(SAMPLE_NEW)
    assert len(rows) > 1000
    assert set(rows[0]) >= {"discount", "cec", "scad_cec", "cec_doc"}
    assert all(x["cec"] is None or isinstance(x["cec"], int) for x in rows)
    # dates are ISO or None — never the '  -   -' placeholder
    assert all(x["scad_cec"] is None or len(x["scad_cec"]) == 10 for x in rows)
    assert all(x["datadl"] is None or len(x["datadl"]) == 10 for x in rows)
    assert any(x["cec"] for x in rows)       # some cheques present
    assert any(x["scad_cec"] for x in rows)  # some cheque due dates parsed


# ── CEC merge (cheque row → invoice row, then drop) ──────────────────────────

def _row(nrdl, cec=0, cec_doc=None, sumdeincas=0.0, scad_cec=None, discount=None):
    return {"nrdl": nrdl, "datadl": "2026-01-01", "term_pl_cl": 0, "plafon": None,
            "numecli": "CLI", "codcli": "C", "cfcli": None, "vtdl": None,
            "sumdeincas": sumdeincas, "factout": f"F{nrdl}", "numeag": "AG",
            "canal": None, "telefon": None, "discount": discount, "cec": cec,
            "scad_cec": scad_cec, "cec_doc": cec_doc, "cec_val": None}


def test_merge_cec():
    rows = [
        _row("INV1", cec=0, sumdeincas=100),
        _row("CHQ1", cec=1, cec_doc="INV1", sumdeincas=100,
             scad_cec="2026-03-01", discount=5),
        _row("ORIG", cec=1, cec_doc="NOPE", sumdeincas=50, scad_cec="2026-04-01"),
        _row("Storno-ORIG", cec=1, cec_doc="NOPE", sumdeincas=-50),
    ]
    out = _etl()._merge_cec(rows)

    by = {r["nrdl"]: r for r in out}
    # matched cheque stamped onto the invoice
    assert by["INV1"]["cec"] == 1
    assert by["INV1"]["cec_val"] == 100        # cheque amount folded onto invoice
    assert by["INV1"]["scad_cec"] == "2026-03-01"
    assert by["INV1"]["cec_doc"] == "INV1"
    assert by["INV1"]["discount"] == 5
    # matched cheque row dropped (no double-count)
    assert "CHQ1" not in by
    assert round(sum(r["sumdeincas"] for r in out), 2) == 100.0
    # unmatched storno pair kept as-is
    assert "ORIG" in by and "Storno-ORIG" in by


def test_merge_cec_multiple():
    # one invoice covered by two cheques → values summed, earliest date kept
    rows = [
        _row("INV1", cec=0, sumdeincas=300),
        _row("CHQ1", cec=1, cec_doc="INV1", sumdeincas=100, scad_cec="2026-05-01"),
        _row("CHQ2", cec=1, cec_doc="INV1", sumdeincas=200, scad_cec="2026-03-15"),
    ]
    out = _etl()._merge_cec(rows)
    by = {r["nrdl"]: r for r in out}
    assert by["INV1"]["cec"] == 1
    assert by["INV1"]["cec_val"] == 300              # 100 + 200
    assert by["INV1"]["scad_cec"] == "2026-03-15"    # earliest of the two
    assert "CHQ1" not in by and "CHQ2" not in by
    # invoices with no cheque keep cec_val = None
    plain = _etl()._merge_cec([_row("INV2", cec=0, sumdeincas=50)])
    assert plain[0]["cec_val"] is None


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
    # disjoint ranges: 0-7 / 8-30 / 31-60 / >60 on each side
    _seed([(0, 100), (5, 100), (20, 100), (45, 100), (100, 100),
           (-3, 100), (-15, 100), (-50, 100), (-200, 100), (-10, -40)])
    k = queries.solduri_kpi()
    assert round(k["nesc7"]) == 200
    assert round(k["nesc30"]) == 100
    assert round(k["nesc60"]) == 100
    assert round(k["nesc60p"]) == 100
    assert round(k["scad7"]) == 100
    assert round(k["scad30"]) == 60
    assert round(k["scad60"]) == 100
    assert round(k["scad60p"]) == 100
    assert round(k["total_scadent"]) == 360
    assert round(k["total_piata"]) == 860
    # reconciliation identity: the 8 disjoint buckets cover everything
    parts = ("nesc7", "nesc30", "nesc60", "nesc60p",
             "scad7", "scad30", "scad60", "scad60p")
    assert round(sum(k[p] for p in parts), 2) == round(k["total_piata"], 2)


def test_kpi_scoped_to_filters():
    # AG0 gets even rows (i=0: due today 100, i=2: 10d overdue 70)
    _seed([(0, 100), (-3, 50), (-10, 70), (-40, 30)])
    k = queries.solduri_kpi(agent="AG0")
    assert round(k["total_piata"]) == 170
    assert round(k["nesc7"]) == 100
    assert round(k["total_scadent"]) == 70
    kq = queries.solduri_kpi(search="CLI1")
    assert round(kq["total_piata"]) == 50  # only i=1 is CLI1


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
        "numecli", "codcli", "numeag", "total", "nesc7", "nesc60p",
        "scad7", "scad60p", "plafon", "zile_restanta_max", "depasit_plafon"}
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
