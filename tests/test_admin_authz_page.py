import sqlite3
import authz


def test_matrix_page_renders(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('mkt','Marketing',0)")
    c.commit()
    c.close()
    html = client.get("/admin/authorizations").get_data(as_text=True)
    assert "Autorizări" in html
    assert "Marketing" in html   # role column header (label)
    assert "P&amp;L" in html or "P&L" in html  # a nav-item row


def test_matrix_post_saves_grants(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('acc','Contabil',0)")
    c.commit()
    c.close()
    # grant acc -> pnl + solduri via checkbox fields "grant:<role>:<navkey>"
    client.post("/admin/authorizations", data={
        "grant:acc:pnl": "on",
        "grant:acc:solduri": "on",
    }, follow_redirects=True)
    assert authz.get_matrix()["acc"] == {"pnl", "solduri"}


def test_admin_role_not_a_column(client):
    html = client.get("/admin/authorizations").get_data(as_text=True)
    # admin must not be an editable column
    assert "grant:admin:" not in html
