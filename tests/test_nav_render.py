import sqlite3
import pytest
from werkzeug.security import generate_password_hash
import authz


@pytest.fixture(scope="module")
def dash_only_client(flask_app, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('dashonly','DashOnly',0)")
    c.execute(
        "INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES (?,?,?,?)",
        ("dashonly_u", "d@test.local", generate_password_hash("p"), "dashonly"),
    )
    c.commit()
    c.close()
    authz.save_matrix({"dashonly": ["dashboard"]})
    cl = flask_app.test_client()
    cl.post("/auth/login", data={"username": "dashonly_u", "password": "p"})
    return cl


def test_admin_sidebar_has_pnl_link(client):
    html = client.get("/").get_data(as_text=True)
    assert "P&amp;L" in html or "P&L" in html
    assert 'data-label="Solduri"' in html


def test_limited_sidebar_hides_denied_links(dash_only_client):
    html = dash_only_client.get("/").get_data(as_text=True)
    assert 'data-label="Dashboard"' in html
    assert 'data-label="Solduri"' not in html
    assert 'data-label="P&amp;L"' not in html
    # empty groups disappear
    assert "Comercial" not in html
