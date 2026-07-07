import db
import pnl_logic


def _seed(rows):
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.executemany(
        """INSERT INTO pnl_balante_raw
           (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
           VALUES('f',?,?,?,?,'',0,0,0,0,0,0,?,0)""",
        rows)
    conn.commit()
    conn.close()


def test_month_subtotals():
    _seed([('torb', 2025, 1, '707', 1000.0), ('torb', 2025, 1, '607', 400.0)])
    m = pnl_logic.compute_pnl_month('torb', 2025, 1)
    assert m['CIFRA DE AFACERI NETA'] == 1000.0
    assert m['COGS NET'] == -400.0
    assert m['MARJA BRUTA'] == 600.0
    assert round(m['Marja bruta %'], 1) == 60.0


def test_month_uses_rulcd_delta():
    _seed([('torb', 2025, 1, '707', 1000.0), ('torb', 2025, 2, '707', 2500.0)])
    assert pnl_logic.compute_pnl_month('torb', 2025, 2)['CIFRA DE AFACERI NETA'] == 1500.0


def test_grup_sums_entities():
    _seed([('torb', 2025, 1, '707', 1000.0), ('tobra', 2025, 1, '707', 500.0)])
    assert pnl_logic.compute_pnl_month('grup', 2025, 1)['CIFRA DE AFACERI NETA'] == 1500.0


def test_alarm_cost_direction():
    cfg = {'alarma_delta_warn': 0.15, 'alarma_delta_err': 0.30, 'directie': 'jos_bine'}
    assert pnl_logic.compute_alarm(150, 100, None, cfg)['delta_severity'] == 'error'
