"""Canonical nav-link registry -- single source of truth for the sidebar,
the Admin -> Autorizari matrix, and route-level 403 enforcement.

Add a nav link HERE (never a raw <a> in base.html). Each item declares the
Flask endpoints it owns so a denied role is blocked, not just hidden.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str                 # bootstrap-icon name, without the 'bi-' prefix
    group: str
    url: str                  # endpoint for url_for() on the link
    endpoints: tuple = ()     # endpoints this feature owns (for the 403 gate)
    blueprint: str | None = None  # shorthand: gate the whole blueprint


GROUPS = ["Analiză", "Comercial", "Operațional", "eCommerce", "Marketing", "AI"]

GROUP_SLUG = {
    "Analiză": "analiza", "Comercial": "comercial", "Operațional": "operational",
    "eCommerce": "ecommerce", "Marketing": "marketing", "AI": "ai",
}

GROUP_COLLAPSIBLE = {"Comercial", "Operațional", "eCommerce", "Marketing"}

NAV_REGISTRY = [
    NavItem("dashboard", "Dashboard", "speedometer2", "Analiză",
            "analytics.dashboard",
            endpoints=("analytics.dashboard", "reports.export_ppt_dashboard")),
    NavItem("team", "Echipă", "people-fill", "Analiză",
            "analytics.team",
            endpoints=("analytics.team", "analytics.agent_detail",
                       "reports.export_ppt_agent")),
    NavItem("clients", "Clienți", "building", "Analiză",
            "analytics.clients",
            endpoints=("analytics.clients", "analytics.client_detail",
                       "reports.export_ppt_client")),
    NavItem("products", "Produse", "box-seam-fill", "Analiză",
            "analytics.products",
            endpoints=("analytics.products", "analytics.brand_detail",
                       "reports.produs_detail")),
    NavItem("profitabilitate", "Profitabilitate", "graph-up-arrow", "Analiză",
            "reports.profitabilitate",
            endpoints=("reports.profitabilitate",
                       "reports.export_ppt_profitabilitate")),
    NavItem("pnl", "P&L", "cash-stack", "Analiză",
            "pnl.pnl", blueprint="pnl"),

    NavItem("preturi", "Prețuri", "tags-fill", "Comercial",
            "pricing.preturi",
            endpoints=("pricing.preturi", "pricing.preturi_sku")),
    NavItem("conditii", "Condiții", "file-earmark-text-fill", "Comercial",
            "pricing.conditii", endpoints=("pricing.conditii",)),
    NavItem("solduri", "Solduri", "cash-coin", "Comercial",
            "solduri.solduri", blueprint="solduri"),
    NavItem("bonus", "Bonus", "trophy-fill", "Comercial",
            "bonus.bonus", blueprint="bonus"),
    NavItem("basilur", "Basilur", "file-earmark-bar-graph-fill", "Comercial",
            "reports.raportare_basilur",
            endpoints=("reports.raportare_basilur",
                       "reports.raportare_basilur_excel",
                       "reports.raportare_basilur_ppt")),

    NavItem("forecast", "Stoc & Comenzi", "boxes", "Operațional",
            "forecast.forecast", endpoints=("forecast.forecast",)),
    NavItem("forecast_setari", "Setări Forecast", "gear-fill", "Operațional",
            "forecast.forecast_setari", endpoints=("forecast.forecast_setari",)),
    NavItem("actualizare", "Actualizare", "cloud-upload-fill", "Operațional",
            "actualizare.actualizare", blueprint="actualizare"),

    NavItem("stoc_sync", "Sincronizare Stoc", "arrow-repeat", "eCommerce",
            "stocuri_emag.stocuri_page", blueprint="stocuri_emag"),
    NavItem("trendyol", "Trendyol Pachete", "bag-fill", "eCommerce",
            "pachete.trendyol_page", endpoints=("pachete.trendyol_page",)),

    NavItem("campanii", "Campanii", "megaphone-fill", "Marketing",
            "campanii.campanii_page", blueprint="campanii"),
    NavItem("postari_ig", "Postări Instagram", "instagram", "Marketing",
            "postari.instagram", endpoints=("postari.instagram",)),
    NavItem("postari_fb", "Postări Facebook", "facebook", "Marketing",
            "postari.facebook", endpoints=("postari.facebook",)),
    NavItem("postari_auto", "Postări Auto", "robot", "Marketing",
            "postari.auto_posts_page", endpoints=("postari.auto_posts_page",)),

    NavItem("ask", "Asistent AI", "chat-dots-fill", "AI",
            "analytics.ask",
            endpoints=("analytics.ask", "analytics.api_ask")),
]

# Sub-routes of blueprints that host more than one nav item. Endpoint -> nav_key.
ENDPOINT_OVERRIDES = {
    # pricing: preturi
    "pricing.api_preturi_landing": "preturi",
    "pricing.api_preturi_vanzare": "preturi",
    "pricing.api_preturi_produs": "preturi",
    "pricing.api_preturi_curs": "preturi",
    "pricing.api_preturi_simuleaza": "preturi",
    "pricing.preturi_articol_nou": "preturi",
    "pricing.api_preturi_articol_nou": "preturi",
    "pricing.preturi_simulator": "preturi",
    "pricing.api_propunere_create": "preturi",
    "pricing.api_propunere_get": "preturi",
    "pricing.api_propunere_delete": "preturi",
    "pricing.propunere_listare_xlsx": "preturi",
    "pricing.api_client_prospect": "preturi",
    "pricing.api_produs_poza": "preturi",
    "pricing.preturi_import_oferta": "preturi",
    "pricing.api_import_oferta": "preturi",
    "pricing.propunere_oferta_xlsx": "preturi",
    "pricing.propunere_fisa_xlsx": "preturi",
    "pricing.preturi_actualizare": "preturi",
    "pricing.api_actualizare_preturi": "preturi",
    # pricing: conditii
    "pricing.api_conditii_create": "conditii",
    "pricing.api_conditii_update": "conditii",
    "pricing.api_conditii_delete": "conditii",
    "pricing.api_termene_create": "conditii",
    "pricing.api_termene_delete": "conditii",
    # forecast: working page
    "forecast.decizii": "forecast",
    "forecast.api_comenzi_drafts": "forecast",
    "forecast.api_comanda_create": "forecast",
    "forecast.api_comanda_get": "forecast",
    "forecast.api_comanda_update": "forecast",
    "forecast.api_comanda_delete": "forecast",
    "forecast.api_comanda_line_add": "forecast",
    "forecast.api_comanda_line_update": "forecast",
    "forecast.api_comanda_line_delete": "forecast",
    "forecast.api_comanda_status": "forecast",
    "forecast.api_forecast_suggest": "forecast",
    "forecast.api_forecast_sku_clients": "forecast",
    "forecast.api_forecast_chat": "forecast",
    "forecast.api_clienti_export_list": "forecast",
    "forecast.api_clienti_export_add": "forecast",
    "forecast.api_clienti_export_delete": "forecast",
    "forecast.api_clienti_search": "forecast",
    "forecast.api_termene_upsert": "forecast",
    "forecast.export_comanda": "forecast",
    "forecast.import_comanda_lines": "forecast",
    "reports.export_comanda_intern": "forecast",
    "reports.export_comanda_furnizor": "forecast",
    "reports.export_expirare_view": "forecast",
    # forecast: settings page
    "forecast.api_forecast_config_get": "forecast_setari",
    "forecast.api_forecast_config_set": "forecast_setari",
    "forecast.api_forecast_tara_save": "forecast_setari",
    "forecast.api_forecast_tara_delete": "forecast_setari",
    "forecast.api_forecast_client_save": "forecast_setari",
    "forecast.api_forecast_client_toggle": "forecast_setari",
    "forecast.api_forecast_termene_save": "forecast_setari",
    # pachete: trendyol
    "pachete.pachete_state": "trendyol",
    "pachete.pachete_products": "trendyol",
    "pachete.pachete_trendyol_preview": "trendyol",
    "pachete.pachete_trendyol_save": "trendyol",
    "pachete.pachete_trendyol_delete": "trendyol",
    "pachete.pachete_trendyol_generate_all": "trendyol",
    "pachete.pachete_trendyol_suggest": "trendyol",
    # stocuri_shopify: Shopify side of the stock-sync page (stoc_sync owns the
    # stocuri_emag blueprint via `blueprint=`; shopify is a separate blueprint
    # backing the same "Sincronizare Stoc" page).
    "stocuri_shopify.stocuri_shopify_page": "stoc_sync",
    "stocuri_shopify.api_shopify_preview": "stoc_sync",
    "stocuri_shopify.api_shopify_sync": "stoc_sync",
    "stocuri_shopify.api_shopify_connection_test": "stoc_sync",
    "stocuri_shopify.api_shopify_sync_history": "stoc_sync",
    "stocuri_shopify.api_shopify_sync_history_rows": "stoc_sync",
    # postari: auto
    "postari.auto_posts_state": "postari_auto",
    "postari.auto_posts_upload": "postari_auto",
    "postari.auto_posts_generate": "postari_auto",
    "postari.auto_posts_regenerate": "postari_auto",
    "postari.auto_posts_approve": "postari_auto",
    "postari.auto_posts_reject": "postari_auto",
    "postari.auto_posts_settings": "postari_auto",
    "postari.auto_posts_photo": "postari_auto",
}

# Business endpoints intentionally NOT gated by the matrix (login-only).
# Doubles as the audit allowlist in Task 6.
UNGATED_ENDPOINTS = {
    "actualizare.api_actualizare_date_status",  # global import chip poll (every page)
    "reports.export_excel",                     # generic multi-feature export
    "postari.postari_ai_generate",              # shared by Instagram + Facebook pages
    # dev-only testing checklist; SHOW_TESTING flag 404s it in prod, and its
    # sidebar link lives outside the nav registry (raw <a>, not a NavItem)
    "forecast.testare",
    # gifting is not a nav item (its sidebar link is commented out) -> login-only
    "pachete.gifting_page",
    "pachete.pachete_gifting_preview",
    "pachete.pachete_gifting_save",
    "pachete.pachete_gifting_delete",
    "pachete.pachete_gifting_suggest",
}
