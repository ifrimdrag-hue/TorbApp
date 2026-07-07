import sqlite3
import pytest
from werkzeug.security import generate_password_hash

import authz


@pytest.fixture(scope="module")
def limited_client(flask_app, db_path):
    """A user with role 'limited' granted only 'dashboard'."""
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('limited','Limited',0)")
    c.execute(
        "INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES (?,?,?,?)",
        ("limited_u", "lim@test.local", generate_password_hash("limpass"), "limited"),
    )
    c.commit()
    c.close()
    authz.save_matrix({"limited": ["dashboard"]})
    cl = flask_app.test_client()
    rv = cl.post("/auth/login", data={"username": "limited_u", "password": "limpass"})
    assert rv.status_code == 302
    return cl


def test_denied_page_returns_403(limited_client):
    assert limited_client.get("/pnl").status_code == 403


def test_granted_page_returns_200(limited_client):
    assert limited_client.get("/").status_code == 200  # analytics.dashboard


def test_denied_api_returns_403_json(limited_client):
    rv = limited_client.post("/pnl/api/scan")
    assert rv.status_code == 403


def test_admin_reaches_everything(client):
    # 'client' fixture is the seeded testadmin (role admin)
    assert client.get("/pnl").status_code == 200
    assert client.get("/solduri-neincasate").status_code == 200


def test_denied_role_cannot_export_gated_report(limited_client):
    assert limited_client.get("/export/clients?an=2026").status_code == 403


def test_granted_dashboard_export_allowed(limited_client):
    assert limited_client.get("/export/dashboard?an=2026").status_code != 403
