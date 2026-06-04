from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./opportunities.db"

    # Google Custom Search API (optional — raises daily limit to 10,000)
    # Get keys at: https://developers.google.com/custom-search/v1/introduction
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # Scraping behavior
    SCRAPE_INTERVAL_HOURS: int = 6
    MAX_RESULTS_PER_QUERY: int = 10
    REQUEST_DELAY_SECONDS: float = 2.0
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
