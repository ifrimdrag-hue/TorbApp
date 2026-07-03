"""Unit tests for the shared RO-first demand split (finding D-DUP)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def test_ro_hu_split_covers_ro_before_export():
    from forecast import forecast_logic as fl

    monthly_ro = {m: 30 for m in range(1, 13)}      # steady RO demand
    monthly_hu = {m: 15 for m in range(1, 13)}      # steady export demand
    lead = 30
    demand_ro = fl._coverage_demand(monthly_ro, lead)
    demand_hu = fl._coverage_demand(monthly_hu, lead)

    # No stock/transit: full demand suggested on each channel
    s0 = fl._ro_hu_split(monthly_ro, monthly_hu, lead, 0)
    assert s0['suggested_ro'] == demand_ro
    assert s0['suggested_export'] == demand_hu

    # Stock exactly covers RO: RO suggestion 0, export still full (no surplus)
    s1 = fl._ro_hu_split(monthly_ro, monthly_hu, lead, demand_ro)
    assert s1['suggested_ro'] == 0
    assert abs(s1['suggested_export'] - demand_hu) < 1e-9

    # Surplus beyond RO offsets the export order
    s2 = fl._ro_hu_split(monthly_ro, monthly_hu, lead, demand_ro + 5)
    assert s2['suggested_ro'] == 0
    assert abs(s2['suggested_export'] - max(0.0, demand_hu - 5)) < 1e-9

    # Enough to cover both channels: nothing suggested
    s3 = fl._ro_hu_split(monthly_ro, monthly_hu, lead, demand_ro + demand_hu + 100)
    assert s3['suggested_ro'] == 0
    assert s3['suggested_export'] == 0
