import authz
import nav_registry as nr

# Blueprints whose endpoints are not business-nav pages and are governed
# elsewhere (auth) or by require_role (admin), or are framework endpoints.
_EXEMPT_BLUEPRINTS = {"auth", "admin", None}
_EXEMPT_ENDPOINTS = {"static", "healthz"}


def test_every_business_endpoint_is_gated_or_allowlisted(flask_app):
    authz.build_endpoint_map(flask_app)
    unmapped = []
    for rule in flask_app.url_map.iter_rules():
        ep = rule.endpoint
        if ep in _EXEMPT_ENDPOINTS or ep.endswith(".static"):
            continue
        bp = ep.rsplit(".", 1)[0] if "." in ep else None
        if bp in _EXEMPT_BLUEPRINTS:
            continue
        if authz.endpoint_nav_key(ep) is None and ep not in nr.UNGATED_ENDPOINTS:
            unmapped.append(ep)
    assert not unmapped, (
        "These endpoints are neither gated nor allow-listed. Assign each to a "
        "nav item (endpoints=/blueprint=/ENDPOINT_OVERRIDES) or add to "
        "UNGATED_ENDPOINTS in app/nav_registry.py:\n  " + "\n  ".join(sorted(unmapped))
    )
