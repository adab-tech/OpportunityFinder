
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    GOOGLE_API_KEY: str | None = None
    GOOGLE_CSE_ID: str | None = None

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

    # Email alerts — RESEND_API_KEY unset means emails are logged, not
    # actually sent (see app/services/email_sender.py). PUBLIC_BASE_URL
    # is used to build the manage-your-alerts link in outgoing emails.
    # Left unset by default so it always reflects the actual API_PORT in
    # local dev; set it explicitly in production (e.g. your Render URL).
    RESEND_API_KEY: str | None = None
    ALERT_FROM_EMAIL: str = "OpportunityFinder <alerts@opportunityfinder.dev>"
    PUBLIC_BASE_URL: str | None = None
    ALERT_DIGEST_INTERVAL_HOURS: int = 168  # weekly

    # Self-hosted analytics — the summary endpoint requires this key
    # (header X-Admin-Key) so visitor stats are never publicly readable.
    # Unset by default: the endpoint refuses all requests until you set it.
    ADMIN_API_KEY: str | None = None

    def cors_origin_list(self) -> list[str]:
        raw = (self.CORS_ORIGINS or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def public_base_url(self) -> str:
        return self.PUBLIC_BASE_URL or f"http://127.0.0.1:{self.API_PORT}"


settings = Settings()
