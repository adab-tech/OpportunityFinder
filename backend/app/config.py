from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database — use Postgres in production (see docs/DEPLOY.md)
    DATABASE_URL: str = "sqlite:///./opportunities.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value):
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg2://", 1)
        if value.startswith("postgresql://") and "+psycopg2" not in value:
            return value.replace("postgresql://", "postgresql+psycopg2://", 1)
        return value

    # Google Custom Search API (optional)
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # Scraping behaviour
    SCRAPE_INTERVAL_HOURS: int = 6
    MAX_RESULTS_PER_QUERY: int = 10
    REQUEST_DELAY_SECONDS: float = 2.0
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3
    RSS_MAX_ENTRIES_PER_FEED: int = 25

    # Server / deployment
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(default=8000, validation_alias=AliasChoices("PORT", "API_PORT"))
    ENABLE_SCHEDULER: bool = True
    CORS_ORIGINS: str = "*"

    def cors_origin_list(self) -> List[str]:
        raw = (self.CORS_ORIGINS or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
