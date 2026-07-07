import db
import queries


def _seed_rows():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.executemany(
        """INSERT INTO pnl_balante_raw
           (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            ('f', 'torb', 2025, 1, '707', 'v', 0, 0, 0, 0, 0, 0, 1000.0, 0),
            ('f', 'torb', 2025, 2, '707', 'v', 0, 0, 0, 0, 0, 0, 2500.0, 0),
            ('f', 'tobra', 2025, 1, '707', 'v', 0, 0, 0, 0, 0, 0, 500.0, 0),
        ],
    )
    conn.commit()
    conn.close()


def test_available_years_and_months():
    _seed_rows()
    assert queries.pnl_available_years() == [2025]
    assert queries.pnl_available_months(2025, 'torb') == [1, 2]
    assert queries.pnl_available_months(2025, 'grup') == [1, 2]


def test_rulcd_and_mapping():
    _seed_rows()
    assert queries.pnl_rulcd('torb', 2025, 2) == {'707': 2500.0}
    mapping = queries.pnl_mapping()
    assert mapping['707'] == ('Venituri marfuri', 1)


def test_alarm_config_loaded():
    cfg = queries.pnl_alarm_config()
    assert cfg['EBITDA']['alarma_delta_err'] == -0.40
