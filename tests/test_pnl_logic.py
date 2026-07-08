import db
import pnl_logic


def _seed(rows):
    """rows: (entitate, an, luna, cont, rulld, rullc, rulcd[, sfd, sfc])."""
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    for r in rows:
        ent, an, luna, cont, rulld, rullc, rulcd = r[:7]
        sfd, sfc = (r[7], r[8]) if len(r) > 7 else (0, 0)
        conn.execute(
            """INSERT INTO pnl_balante_raw
               (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
               VALUES('f',?,?,?,?,'',0,0,?,?,?,?,?,0)""",
            (ent, an, luna, cont, sfd, sfc, rulld, rullc, rulcd))
    conn.commit()
    conn.close()


def test_month_subtotals():
    # Revenue 707 comes from rullc (semn +1); expense 607 from rulld (semn -1).
    _seed([('torb', 2025, 1, '707', 0, 1000.0, 1000.0),
           ('torb', 2025, 1, '607', 400.0, 0, 400.0)])
    m = pnl_logic.compute_pnl_month('torb', 2025, 1)
    assert m['CIFRA DE AFACERI NETA'] == 1000.0
    assert m['COGS NET'] == -400.0
    assert m['MARJA BRUTA'] == 600.0
    assert round(m['Marja bruta %'], 1) == 60.0


def test_month_uses_own_turnover_no_prior_dependency():
    # Only February exists (no January). The month must still read its OWN rullc,
    # never the cumulative — this is the C2 bug the redesign fixes.
    _seed([('torb', 2025, 2, '707', 0, 1500.0, 4000.0)])
    assert pnl_logic.compute_pnl_month('torb', 2025, 2)['CIFRA DE AFACERI NETA'] == 1500.0


def test_grup_sums_entities():
    _seed([('torb', 2025, 1, '707', 0, 1000.0, 1000.0),
           ('tobra', 2025, 1, '707', 0, 500.0, 500.0)])
    assert pnl_logic.compute_pnl_month('grup', 2025, 1)['CIFRA DE AFACERI NETA'] == 1500.0


def test_ytd_from_cumulative_rulcd():
    # YTD reads cumulative rulcd at the through-month, so it equals the account
    # balance even if intermediate months are absent.
    _seed([('torb', 2025, 1, '707', 0, 1000.0, 1000.0),
           ('torb', 2025, 3, '707', 0, 1200.0, 3300.0)])
    ytd = pnl_logic.compute_ytd('torb', 2025, 3)
    assert ytd['CIFRA DE AFACERI NETA'] == 3300.0


def test_reconciliere_121_ok():
    # Net profit YTD = 707 (rulcd 1000, +1) - 607 (rulcd 400, -1) = 600.
    # 121 sfc-sfd = 600 -> reconciled.
    _seed([('torb', 2025, 1, '707', 0, 1000.0, 1000.0),
           ('torb', 2025, 1, '607', 400.0, 0, 400.0),
           ('torb', 2025, 1, '121', 0, 0, 0, 0.0, 600.0)])
    rec = pnl_logic.reconciliere_121('torb', 2025, 1)
    assert rec['ok'] is True
    assert rec['pn'] == 600.0 and rec['sold'] == 600.0 and rec['diff'] == 0.0


def test_reconciliere_121_diff():
    _seed([('torb', 2025, 1, '707', 0, 1000.0, 1000.0),
           ('torb', 2025, 1, '121', 0, 0, 0, 0.0, 900.0)])
    rec = pnl_logic.reconciliere_121('torb', 2025, 1)
    assert rec['ok'] is False
    assert rec['diff'] == 100.0


def test_monthly_crosscheck_warns_on_divergence():
    # Jan then Feb; 628 (expense, rulld) Feb rullc/rulld says 300 but cumulative
    # rulcd jumped by 800 (prior-period correction) -> divergence, warning fires.
    _seed([('torb', 2025, 1, '628', 500.0, 500.0, 500.0),
           ('torb', 2025, 2, '628', 300.0, 300.0, 1300.0)])
    warns = pnl_logic.compute_pnl_month_warnings('torb', 2025, 2)
    assert 'Servicii terti / logistica / marketing' in warns
    assert abs(warns['Servicii terti / logistica / marketing']['monthly'] - -300.0) < 0.01


def test_monthly_crosscheck_silent_when_consistent():
    _seed([('torb', 2025, 1, '628', 500.0, 500.0, 500.0),
           ('torb', 2025, 2, '628', 300.0, 300.0, 800.0)])
    assert pnl_logic.compute_pnl_month_warnings('torb', 2025, 2) == {}


def test_monthly_crosscheck_skips_without_prior():
    _seed([('torb', 2025, 2, '628', 300.0, 300.0, 800.0)])
    assert pnl_logic.compute_pnl_month_warnings('torb', 2025, 2) == {}


def test_alarm_cost_direction():
    cfg = {'alarma_delta_warn': 0.15, 'alarma_delta_err': 0.30, 'directie': 'jos_bine'}
    assert pnl_logic.compute_alarm(150, 100, None, cfg)['delta_severity'] == 'error'
