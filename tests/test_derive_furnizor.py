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
