
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

    # You.com Search API (optional) — a second official discovery source,
    # tried after Google's API (if configured) and before the unofficial
    # scraping fallback. See app/scrapers/google_scraper.py.
    YOU_API_KEY: str | None = None

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

    # Deadline reminders for saved opportunities — sent once per saved
    # item when its deadline is this many days away or closer, so saving
    # something doesn't silently guarantee remembering it.
    SAVED_REMINDER_DAYS_BEFORE: int = 3
    SAVED_REMINDER_INTERVAL_HOURS: int = 24

    # Admin login (analytics + moderation queue) — superseded the old
    # shared X-Admin-Key header with a real email/password account and a
    # signed session cookie (see app/security.py, app/routes/admin_auth.py).
    # ADMIN_PASSWORD_HASH is generated once via
    # `scripts/hash_admin_password.py` and pasted into the deployment's
    # env vars — the plaintext password itself is never stored anywhere.
    # All three must be set for admin login to work; unset means the
    # admin endpoints refuse every request (fail closed, same posture as
    # the old key check).
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD_HASH: str | None = None
    # Signs the admin session cookie. Must be set explicitly in
    # production — an unset/ephemeral key means every restart invalidates
    # all sessions, which is a usability problem, not a security one, but
    # still worth setting deliberately.
    SESSION_SECRET_KEY: str | None = None
    # The session cookie is Secure (HTTPS-only) by default, correct for
    # the real deployment. Local dev over plain http:// needs this set
    # to false or the browser silently refuses to store the cookie.
    SESSION_COOKIE_SECURE: bool = True

    def cors_origin_list(self) -> list[str]:
        raw = (self.CORS_ORIGINS or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def public_base_url(self) -> str:
        return self.PUBLIC_BASE_URL or f"http://127.0.0.1:{self.API_PORT}"


settings = Settings()
