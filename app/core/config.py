from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_path: str = "./data/invoices.db"

    llm_provider: str = "ollama"  # "ollama" | "gemini"
    llm_base_url: str = "http://ollama:11434"
    llm_model: str = "qwen3:1.7b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    rustfs_endpoint: str = "http://rustfs:9000"
    rustfs_access_key: str = "rustfsadmin"
    rustfs_secret_key: str = "rustfsadmin"
    rustfs_bucket_invoices: str = "invoices"
    rustfs_bucket_exports: str = "exports"

    # IMAP email listener
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_use_ssl: bool = True
    email_listener_enabled: bool = False
    email_poll_interval: int = 300  # seconds

    # Notifications
    notification_type: str = "console"  # "telegram" | "slack" | "console"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    app_base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env"}

@lru_cache
def get_settings() -> Settings:
    return Settings()