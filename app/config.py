from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env", override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    emag_api_url: str = "https://marketplace-api.emag.ro/api-3"
    emag_username: str = ""
    emag_password: str = ""
    emag_warehouse_id: int = 1
    emag_stock_safety_threshold: int = 5

    shopify_shop_domain: str = ""
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_api_version: str = "2025-04"
    shopify_location_id: str = ""
    shopify_stock_safety_threshold: int = 5

    log_level: str = "INFO"

    pnl_torb_folder: str = r"G:\My Drive\1_a_Torb\Buget2026\Balante 2025"
    pnl_tobra_folder: str = r"G:\My Drive\1_a_Torb\Buget2026\Balante 2025\balante"

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"


settings = Settings()
