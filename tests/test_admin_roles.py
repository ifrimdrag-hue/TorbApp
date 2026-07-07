import sqlite3


def test_create_role(client, db_path):
    rv = client.post("/admin/roles/new",
                     data={"name": "contabil", "label": "Contabil"},
                     follow_redirects=True)
    assert rv.status_code == 200
    c = sqlite3.connect(db_path)
    row = c.execute("SELECT label, is_system FROM adm_roles WHERE name='contabil'").fetchone()
    c.close()
    assert row == ("Contabil", 0)


def test_cannot_delete_system_role(client, db_path):
    c = sqlite3.connect(db_path)
    aid = c.execute("SELECT id FROM adm_roles WHERE name='admin'").fetchone()[0]
    c.close()
    client.post(f"/admin/roles/{aid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    still = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='admin'").fetchone()[0]
    c.close()
    assert still == 1


def test_cannot_delete_role_in_use(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('inuse','InUse',0)")
    rid = c.execute("SELECT id FROM adm_roles WHERE name='inuse'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO adm_users (username,email,password_hash,role) VALUES ('u_inuse','x@x.l','h','inuse')")
    c.commit()
    c.close()
    client.post(f"/admin/roles/{rid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    still = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='inuse'").fetchone()[0]
    c.close()
    assert still == 1


def test_delete_unused_custom_role(client, db_path):
    c = sqlite3.connect(db_path)
    c.execute("INSERT OR IGNORE INTO adm_roles (name,label,is_system) VALUES ('temp','Temp',0)")
    rid = c.execute("SELECT id FROM adm_roles WHERE name='temp'").fetchone()[0]
    c.commit()
    c.close()
    client.post(f"/admin/roles/{rid}/delete", follow_redirects=True)
    c = sqlite3.connect(db_path)
    gone = c.execute("SELECT COUNT(*) FROM adm_roles WHERE name='temp'").fetchone()[0]
    c.close()
    assert gone == 0
