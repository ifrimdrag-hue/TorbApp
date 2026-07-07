import importlib.util
import os

ETL = os.path.join(os.path.dirname(__file__), "..", "etl")


def _load(module_file):
    path = os.path.join(ETL, module_file)
    spec = importlib.util.spec_from_file_location(module_file[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stoc():
    return _load("import_stoc.py").derive_furnizor


def _erp():
    return _load("import_vanzari_erp.py")._furnizor_from_prefix


def _tobra():
    return _load("import_vanzari_tobra_auchan.py").derive_furnizor


ORGANSIA_SKU = "B.ECO ORGANSIA APPLE CINNAMON AND ROSEHIP 1,8GX18E 19322"
BASILUR_SKU = "B.CEYLON GOLD 100G"
KL_SKU = "KL SOME GREEN TEA"
TS_SKU = "TS SOME BLACK TEA"


def test_stoc_organsia():
    assert _stoc()(ORGANSIA_SKU) == "Organsia"

def test_stoc_basilur_unaffected():
    assert _stoc()(BASILUR_SKU) == "Basilur"

def test_stoc_kl_ts_unaffected():
    f = _stoc()
    assert f(KL_SKU) == "KingsLeaf"
    assert f(TS_SKU) == "Tipson"

def test_erp_organsia():
    assert _erp()(ORGANSIA_SKU) == "Organsia"

def test_erp_basilur_unaffected():
    assert _erp()(BASILUR_SKU) == "Basilur"

def test_tobra_organsia():
    assert _tobra()(ORGANSIA_SKU, {}, None) == "Organsia"

def test_tobra_basilur_unaffected():
    assert _tobra()(BASILUR_SKU, {}, None) == "Basilur"

def test_tobra_sku_name_beats_colliding_cod_lookup():
    # Tobra cod_produs collides with Torb ERP codes (real case: Tobra 1508 =
    # KL English Breakfast, Torb 1508 = C.Goplana/Celmar) — the SKU-name rule
    # must win over the cod_produs lookup.
    f = _tobra()
    assert f("KL ENGLISH BREAKFAST (25X2G) 90205", {"1508": "Celmar"}, "1508") == "KingsLeaf"
    assert f("T.CIOC ALBA CU CEAI MATCHA FZG 75GR-524", {"77": "Basilur"}, "77") == "Toras"

def test_tobra_cod_lookup_still_used_when_name_unknown():
    f = _tobra()
    assert f("PRODUS FARA REGULA DE PREFIX", {"42": "Leonex"}, "42") == "Leonex"
    assert f("PRODUS FARA REGULA DE PREFIX", {}, "42") == "Altele"

def test_tobra_extract_cod_mare():
    mod = _load("import_vanzari_tobra_auchan.py")
    f = mod.extract_cod_mare
    assert f("KL EARL GREY (25X2G) 90204-4792252942417") == "90204"
    assert f("KL CEAI EARL GREY (25X2G) 90204-4792252942417") == "90204"
    assert f("B.HORECA ENGLISH BREAKFAST (2G*100EN) 70312") == "70312"
    assert f("DISCURI DEMACHIANTE LEONEX 120BUC (5754) (5948593000890)") == "5754"
    assert f("C.GOPLANA JELEURI CIRESE 190G") is None
    assert mod._norm_cod_mare("90204-00") == "90204"

def test_tobra_identity_by_cod_mare_not_cod_produs():
    # Tobra cod 1509 collides with Torb 1509 (C.Goplana) — identity must come
    # from the cod mare in the name: adopt the ERP spelling + Torb cod 1661.
    mod = _load("import_vanzari_tobra_auchan.py")
    lookup = {"90204": ("KL CEAI EARL GREY (25X2G) 90204-4792252942417", "1661")}
    rows = [{"datadl": 45000.0, "den_b": "KL EARL GREY (25X2G) 90204-4792252942417",
             "codprod": "1509", "cantit": 6, "pvanz": 8.5}]
    rec = mod.process_rows(rows, {}, 0, lookup)[0]
    assert rec["sku"] == "KL CEAI EARL GREY (25X2G) 90204-4792252942417"
    assert rec["cod_produs"] == "1661"
    assert rec["cod_tobra"] == "1509"
    assert rec["furnizor"] == "KingsLeaf"

def test_tobra_no_cod_mare_keeps_file_name():
    # No cod mare in the name -> keep the Tobra spelling; never rename via
    # the colliding cod_produs.
    mod = _load("import_vanzari_tobra_auchan.py")
    rows = [{"datadl": 45000.0, "den_b": "PRODUS NOU FARA COD",
             "codprod": "1508", "cantit": 1, "pvanz": 2.0}]
    rec = mod.process_rows(rows, {"1508": "Celmar"}, 0,
                           {"90205": ("KL ENGLISH BREAKFAST", "1660")})[0]
    assert rec["sku"] == "PRODUS NOU FARA COD"
    assert rec["cod_produs"] == "1508"

HORECA_TS_SKU = "HORECA TS WELLNESS IMMUNE BOOSTER (1,3GX100) 80226"
HORECA_KL_SKU = "HORECA KL ROYAL ASSAM (2GX100)"
HORECA_BASILUR_SKU = "HORECA COLD BREW STRAWBERRY CUCUMBER MINT 2GX100E 72122"

def test_horeca_virtual_brands_stay_separate():
    # HORECA formats of the virtual sub-brands must NOT fall into the generic
    # HORECA -> Basilur rule (real case: 9 'HORECA TS' SKUs filed as Basilur).
    for f in (_stoc(), _erp()):
        assert f(HORECA_TS_SKU) == "Tipson"
        assert f(HORECA_KL_SKU) == "KingsLeaf"
        assert f(HORECA_BASILUR_SKU) == "Basilur"
    t = _tobra()
    assert t(HORECA_TS_SKU, {}, None) == "Tipson"
    assert t(HORECA_KL_SKU, {}, None) == "KingsLeaf"
    assert t(HORECA_BASILUR_SKU, {}, None) == "Basilur"
