import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class TelegramConfig:
    api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    session_name: str = os.getenv("TELEGRAM_SESSION_NAME", "ads_bot")
    max_concurrent_transmissions: int = int(os.getenv("TELEGRAM_MAX_CONCURRENT_TRANSMISSIONS", "1"))
    owner_id: int = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
    log_channel_id: int = int(os.getenv("TELEGRAM_LOG_CHANNEL_ID", "0"))
    cache_channel_id: int = int(os.getenv("TELEGRAM_CACHE_CHANNEL_ID", "0"))
    start_image: str = os.getenv("TELEGRAM_START_IMAGE", "")
    main_bot_username: str = ""
    hub_bot_token: str = os.getenv("HUB_BOT_TOKEN", "")
    hub_session_name: str = os.getenv("TELEGRAM_HUB_SESSION_NAME", "hub_bot")

    @property
    def main_bot_id(self) -> int:
        if self.bot_token and ":" in self.bot_token:
            try:
                return int(self.bot_token.split(":")[0])
            except:
                pass
        return 0

@dataclass
class DatabaseConfig:
    uri: str = os.getenv("DATABASE_URI", "mongodb://localhost:27017")
    database_name: str = os.getenv("DATABASE_NAME", "ads_bot")

@dataclass
class AppConfig:
    debug: bool = os.getenv("APP_DEBUG", "False").lower() in ("true", "1", "t")
    webhook: bool = os.getenv("APP_WEBHOOK", "False").lower() in ("true", "1", "t")
    log_level: str = os.getenv("APP_LOG_LEVEL", "INFO")
    name: str = os.getenv("APP_NAME", "Ads Bot")
    description: str = os.getenv("APP_DESCRIPTION", "A simple ads bot")
    version: str = os.getenv("APP_VERSION", "1.0.0")
    timezone: str = os.getenv("APP_TIMEZONE", "UTC")
    cache_dir: str = os.getenv("APP_CACHE_DIR", "cache")
    max_buttons_per_line: int = int(os.getenv("APP_MAX_BUTTONS_PER_LINE", "5"))
    max_columns: int = int(os.getenv("APP_MAX_COLUMNS", "5"))
    max_rows: int = int(os.getenv("APP_MAX_ROWS", "10"))
    max_buttons: int = int(os.getenv("APP_MAX_BUTTONS", "50"))

@dataclass
class RedisConfig:
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: str = os.getenv("REDIS_PASSWORD", "")
    db: int = int(os.getenv("REDIS_DB", "0"))
    cache_ttl: int = int(os.getenv("REDIS_CACHE_TTL", "3600"))

@dataclass
class UserConfig:
    max_channels: int = int(os.getenv("USER_MAX_CHANNELS", "5"))

@dataclass
class Config:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    application: AppConfig = field(default_factory=AppConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    users: UserConfig = field(default_factory=UserConfig)

config = Config()