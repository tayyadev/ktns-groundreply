from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://groundreply:local-dev-postgres-only@localhost:5432/groundreply"
    jwt_secret: str = ""
    app_origin: str = "http://localhost:8080"
    cookie_secure: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    max_cosine_distance: float = 0.65
    llm_timeout_seconds: int = 45
    max_ticket_question_chars: int = 6000
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
