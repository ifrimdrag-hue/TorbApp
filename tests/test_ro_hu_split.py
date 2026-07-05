"""Unit tests for the RO-first demand split in split_with_safety (finding D-DUP).

With coef=0 (no safety stock) and no per-country breakdown, split_with_safety
reduces to the legacy RO-first logic: available stock covers the RO coverage
demand first, only the surplus offsets the separate export order.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def test_split_with_safety_covers_ro_before_export():
    from forecast import forecast_logic as fl

    monthly_ro = {m: 30 for m in range(1, 13)}      # steady RO demand
    monthly_hu = {m: 15 for m in range(1, 13)}      # steady export demand
    lead = 30
    demand_ro = fl._coverage_demand(monthly_ro, lead, 30)
    demand_hu = fl._coverage_demand(monthly_hu, lead, 30)

    def split(available):
        # coef=0, buc_cutie=None (round to unit), no monthly_piete → legacy path
        return fl.split_with_safety(monthly_ro, monthly_hu, lead, available,
                                    0.0, 0.0, 0.0, 30, None)

    # No stock/transit: full demand suggested on each channel
    s0 = split(0)
    assert s0['suggested_ro'] == round(demand_ro)
    assert s0['suggested_export'] == round(demand_hu)

    # Stock exactly covers RO: RO suggestion 0, export still full (no surplus)
    s1 = split(demand_ro)
    assert s1['suggested_ro'] == 0
    assert s1['suggested_export'] == round(demand_hu)

    # Surplus beyond RO offsets the export order
    s2 = split(demand_ro + 5)
    assert s2['suggested_ro'] == 0
    assert s2['suggested_export'] == round(max(0.0, demand_hu - 5))

    # Enough to cover both channels: nothing suggested
    s3 = split(demand_ro + demand_hu + 100)
    assert s3['suggested_ro'] == 0
    assert s3['suggested_export'] == 0
