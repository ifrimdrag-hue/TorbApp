import sqlite3
import pytest

import authz  # app/ is on sys.path via conftest
import nav_registry as nr


@pytest.fixture
def seeded(db_path):
    # conftest already ran migration 0037; ensure a custom empty role exists
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('contabil','Contabil',0)")
    c.commit()
    c.close()
    yield db_path
    c = sqlite3.connect(db_path)
    c.execute("DELETE FROM adm_roles WHERE name='contabil'")
    c.execute("DELETE FROM adm_role_nav WHERE role_id NOT IN (SELECT id FROM adm_roles)")
    c.commit()
    c.close()


def test_admin_sees_all_keys(seeded):
    assert authz.granted_nav_keys("admin") == {i.key for i in nr.NAV_REGISTRY}


def test_seeded_manager_sees_all(seeded):
    assert authz.granted_nav_keys("manager") == {i.key for i in nr.NAV_REGISTRY}


def test_new_role_is_deny_by_default(seeded):
    assert authz.granted_nav_keys("contabil") == set()
    assert authz.can_access_nav("contabil", "pnl") is False


def test_unknown_role_sees_nothing(seeded):
    assert authz.granted_nav_keys("does-not-exist") == set()


def test_save_and_get_matrix(seeded):
    authz.save_matrix({"contabil": ["pnl", "solduri"], "viewer": ["dashboard"]})
    m = authz.get_matrix()
    assert m["contabil"] == {"pnl", "solduri"}
    assert m["viewer"] == {"dashboard"}
    assert "admin" not in m  # admin never in the matrix


def test_nav_tree_filters_and_groups(seeded):
    authz.save_matrix({"contabil": ["pnl"]})
    tree = authz.nav_tree("contabil")
    # only the Analiză group with the pnl item survives
    assert len(tree) == 1
    assert tree[0]["group"] == "Analiză"
    assert [i.key for i in tree[0]["items"]] == ["pnl"]


def test_endpoint_map_expands_blueprint_and_overrides(flask_app):
    m = authz.build_endpoint_map(flask_app)
    assert m.get("pnl.pnl") == "pnl"           # blueprint shorthand
    assert m.get("pnl.api_upload") == "pnl"    # blueprint shorthand covers sub-routes
    assert m.get("pricing.api_conditii_create") == "conditii"  # override
    assert m.get("forecast.api_forecast_config_set") == "forecast_setari"  # override
    assert "actualizare.api_actualizare_date_status" not in m  # ungated
    assert authz.endpoint_nav_key("solduri.solduri") == "solduri"
