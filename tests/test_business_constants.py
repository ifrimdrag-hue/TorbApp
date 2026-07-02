from business_constants import (
    AUCHAN_AGENT,
    AUCHAN_CLIENT_NAME,
    AUCHAN_COD_CLIENT,
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
    TOBRA_COST_WINDOW_DAYS,
    TOBRA_INVOICE_PREFIX,
)


def test_auchan_tobra_values():
    assert AUCHAN_COD_CLIENT == "732"
    assert AUCHAN_CLIENT_NAME == "AUCHAN ROMANIA SA"
    assert AUCHAN_TIP_CLIENT == "HYPERMARKET"
    assert AUCHAN_AGENT == "Oana Filip"
    assert TOBRA_COD_CLIENT == "719"
    assert TOBRA_INVOICE_PREFIX == "TOBRA"
    assert TOBRA_COST_WINDOW_DAYS == 30


def test_client_codes_are_strings():
    # tranzactii.cod_client is TEXT -- int constants would silently break queries
    assert isinstance(AUCHAN_COD_CLIENT, str)
    assert isinstance(TOBRA_COD_CLIENT, str)
