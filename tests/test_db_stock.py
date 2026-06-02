def test_db_stock_query_returns_results(flask_app):
    """db_stock.query() works and returns rows from stock.db."""
    import db_stock
    with flask_app.app_context():
        rows = db_stock.query("SELECT 1 AS n")
    assert isinstance(rows, list)
    assert rows[0]['n'] == 1
