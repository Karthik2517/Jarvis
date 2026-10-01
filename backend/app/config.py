from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JARVIS API"
    database_path: str = "./jarvis.db"
    app_secret: str = "local-development-secret-change-me"
    frontend_origin: str = "http://localhost:5173"
    paper_starting_cash: float = 1_000_000
    max_order_quantity: int = 1_000
    max_order_notional: float = 500_000
    allow_short_selling: bool = True
    demo_strategy_key: str = "demo-strategy-key"
    upstox_access_token: str = ""
    upstox_api_base_url: str = "https://api.upstox.com"
    upstox_sandbox_access_token: str = ""
    upstox_sandbox_base_url: str = "https://api-sandbox.upstox.com"
    upstox_order_base_url: str = "https://api-hft.upstox.com"
    live_trading_enabled: bool = False
    allow_live_strategies: bool = False
    token_ttl_seconds: int = 86_400

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
