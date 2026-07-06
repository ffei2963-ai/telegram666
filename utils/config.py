import os
import yaml
from dataclasses import dataclass, field
from typing import Optional

CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")


@dataclass
class Config:
    bot_token: str = ""
    admin_user_ids: list[int] = field(default_factory=list)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    db_path: str = "data/tgcloud.db"
    sessions_dir: str = "data/sessions"
    uploads_dir: str = "data/uploads"
    max_concurrent_accounts: int = 5
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        c = cls()
        c.bot_token = os.getenv("TG_BOT_TOKEN", "")
        admin_ids = os.getenv("TG_ADMIN_IDS", "")
        if admin_ids:
            c.admin_user_ids = [int(x.strip()) for x in admin_ids.split(",") if x.strip()]
        c.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        c.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        c.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        c.db_path = os.getenv("DB_PATH", "data/tgcloud.db")
        c.sessions_dir = os.getenv("SESSIONS_DIR", "data/sessions")
        c.uploads_dir = os.getenv("UPLOADS_DIR", "data/uploads")
        c.max_concurrent_accounts = int(os.getenv("MAX_CONCURRENT_ACCOUNTS", "5"))
        c.log_level = os.getenv("LOG_LEVEL", "INFO")
        return c

    @classmethod
    def from_yaml(cls, path: str = DEFAULT_CONFIG_PATH) -> "Config":
        c = cls()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                if hasattr(c, k):
                    setattr(c, k, v)
        return c


config = Config.from_env()
