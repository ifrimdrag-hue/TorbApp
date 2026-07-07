def test_users_page_has_three_tabs(client):
    html = client.get("/admin/users").get_data(as_text=True)
    assert "Utilizatori" in html
    assert "Mentenanță DB" in html
    assert "Autorizări" in html


def test_openclaw_moved_to_db_tab(client):
    users_html = client.get("/admin/users").get_data(as_text=True)
    db_html = client.get("/admin/db").get_data(as_text=True)
    assert "OpenClaw" not in users_html
    assert "OpenClaw" in db_html
