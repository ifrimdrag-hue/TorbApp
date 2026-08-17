"""Business constants shared across app/ and etl/.

Home for hard-coded business facts (client codes, agent names, business
rule parameters). NOT for deployment/env settings -- those live in
app/config.py (env-overridable; business facts must never be).

Convention: each constant group carries a 'Used by:' comment listing the
modules that import it. Update the list when you add a consumer, so
usage is visible here without searching the codebase.
"""

# --- Auchan / Tobra invoicing exception ------------------------------------
# Torb->Auchan sales are invoiced through the intermediary Tobra Invest SRL.
# The ERP import diverts Torb->Tobra lines (cod 719) to the corr_vanzari_tobra
# cost table; the Auchan import injects Tobra->Auchan invoices as Torb sales
# (client 732, agent Oana Filip) and overrides pret_cumparare with the true
# Torb cost averaged over TOBRA_COST_WINDOW_DAYS. Details:
# docs/BUSINESS_LOGIC.md section 3.
#
# Used by:
#   etl/import_vanzari_tobra_auchan.py
#   etl/import_vanzari_erp.py
AUCHAN_COD_CLIENT = "732"
AUCHAN_CLIENT_NAME = "AUCHAN ROMANIA SA"
AUCHAN_TIP_CLIENT = "HYPERMARKET"
AUCHAN_AGENT = "Oana Filip"

TOBRA_COD_CLIENT = "719"
TOBRA_INVOICE_PREFIX = "TOBRA"
TOBRA_COST_WINDOW_DAYS = 30

# --- Client mergers (acquisitions / rebranding) -----------------------------
# Profi Rom Food SRL was acquired by Mega Image SRL, so every Profi sale,
# balance and commercial condition now belongs to Mega Image. The ERP still
# exports the absorbed client code on historical rows, so the rewrite runs on
# every import instead of once. Physical location (oras/judet/adresa) is left
# untouched -- the stores did not move, only the commercial identity changed.
#
# Key = absorbed cod_client; value = the surviving client's identity.
# Details: docs/BUSINESS_LOGIC.md section 3.
#
# Used by:
#   etl/client_merges.py
CLIENT_MERGES = {
    "973": {
        "sursa":      "PROFI ROM FOOD SRL",
        "client":     "MEGA IMAGE SRL",
        "cod_client": "4909",
        "cui_client": "RO6719278",
        "tip_client": "SUPERMARKET",
    },
}
