from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: SecretStr
    database_url: str
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    webhook_attempts: int = 3
    webhook_base_delay_seconds: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
