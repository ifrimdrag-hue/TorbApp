import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "app"))
import nav_registry as nr


def test_keys_are_unique():
    keys = [i.key for i in nr.NAV_REGISTRY]
    assert len(keys) == len(set(keys))


def test_every_item_group_is_declared():
    for i in nr.NAV_REGISTRY:
        assert i.group in nr.GROUPS


def test_every_item_has_a_gate():
    # each item must declare either a blueprint or explicit endpoints
    for i in nr.NAV_REGISTRY:
        assert i.blueprint or i.endpoints, f"{i.key} has no gate"


def test_collapsible_groups_have_slugs():
    for g in nr.GROUP_COLLAPSIBLE:
        assert g in nr.GROUP_SLUG


def test_expected_keys_present():
    keys = {i.key for i in nr.NAV_REGISTRY}
    assert {"dashboard", "pnl", "preturi", "forecast", "trendyol", "ask"} <= keys
