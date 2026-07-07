"""Role -> nav-key authorization + endpoint gate resolution.

Deny-by-default. `admin` is a superuser and bypasses every check.
"""
import sqlite3

from paths import DB_PATH
from nav_registry import (
    NAV_REGISTRY, GROUPS, GROUP_SLUG, GROUP_COLLAPSIBLE,
    ENDPOINT_OVERRIDES, UNGATED_ENDPOINTS,
)

ADMIN_ROLE = "admin"
_ALL_KEYS = {item.key for item in NAV_REGISTRY}
_endpoint_map: dict[str, str] = {}


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def build_endpoint_map(app) -> dict:
    """endpoint -> nav_key, from registry + overrides, using the app url_map.
    Call once after all blueprints are registered."""
    global _endpoint_map
    m: dict[str, str] = {}
    bp_owner = {i.blueprint: i.key for i in NAV_REGISTRY if i.blueprint}
    for rule in app.url_map.iter_rules():
        ep = rule.endpoint
        bp = ep.rsplit(".", 1)[0] if "." in ep else None
        if bp in bp_owner:
            m[ep] = bp_owner[bp]
    for item in NAV_REGISTRY:
        for ep in item.endpoints:
            m[ep] = item.key
    m.update(ENDPOINT_OVERRIDES)
    for ep in UNGATED_ENDPOINTS:
        m.pop(ep, None)
    _endpoint_map = m
    return m


def endpoint_nav_key(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    return _endpoint_map.get(endpoint)


def granted_nav_keys(role: str) -> set:
    if role == ADMIN_ROLE:
        return set(_ALL_KEYS)
    with _conn() as c:
        row = c.execute("SELECT id FROM adm_roles WHERE name=?", (role,)).fetchone()
        if not row:
            return set()
        rows = c.execute(
            "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (row["id"],)
        ).fetchall()
    return {r[0] for r in rows}


def can_access_nav(role: str, nav_key: str) -> bool:
    if role == ADMIN_ROLE:
        return True
    return nav_key in granted_nav_keys(role)


def nav_tree(role: str) -> list:
    keys = granted_nav_keys(role)
    tree = []
    for g in GROUPS:
        items = [i for i in NAV_REGISTRY if i.group == g and i.key in keys]
        if items:
            tree.append({
                "group": g,
                "slug": GROUP_SLUG[g],
                "collapsible": g in GROUP_COLLAPSIBLE,
                "items": items,
            })
    return tree


def all_roles() -> list:
    with _conn() as c:
        return c.execute(
            "SELECT id, name, label, is_system FROM adm_roles "
            "ORDER BY is_system DESC, label"
        ).fetchall()


def get_matrix() -> dict:
    result = {}
    with _conn() as c:
        roles = c.execute(
            "SELECT id, name FROM adm_roles WHERE name!=?", (ADMIN_ROLE,)
        ).fetchall()
        for r in roles:
            rows = c.execute(
                "SELECT nav_key FROM adm_role_nav WHERE role_id=?", (r["id"],)
            ).fetchall()
            result[r["name"]] = {x[0] for x in rows}
    return result


def save_matrix(grants: dict) -> None:
    """Replace all non-admin grants. grants = {role_name: [nav_key, ...]}.
    Only keys in the registry and roles in the DB are persisted."""
    with _conn() as c:
        name_to_id = {
            r["name"]: r["id"]
            for r in c.execute(
                "SELECT id, name FROM adm_roles WHERE name!=?", (ADMIN_ROLE,)
            ).fetchall()
        }
        ids = list(name_to_id.values())
        if ids:
            c.execute(
                "DELETE FROM adm_role_nav WHERE role_id IN (%s)"
                % ",".join("?" * len(ids)),
                ids,
            )
        rows = []
        for role_name, keys in grants.items():
            rid = name_to_id.get(role_name)
            if rid is None:
                continue
            for k in keys:
                if k in _ALL_KEYS:
                    rows.append((rid, k))
        c.executemany(
            "INSERT OR IGNORE INTO adm_role_nav (role_id, nav_key) VALUES (?,?)",
            rows,
        )
        c.commit()
