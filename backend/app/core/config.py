from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "local"
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 2
    DB_MAX_OVERFLOW: int = 3
    DB_POOL_TIMEOUT: float = 30.0
    DB_COMMAND_TIMEOUT: float = 30.0
    DB_MAX_INACTIVE_LIFETIME: float = 120.0
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    EXTENSION_HANDOFF_SECRET: str = ""
    EXTENSION_ALLOWED_IDS: str = ""
    ENCRYPTION_KEY: str = ""
    CORS_ALLOWED_ORIGINS: str = ""
    CORS_ALLOWED_ORIGIN_REGEX: str = ""
    GHL_PIT: str = ""
    GHL_SALES_LOCATION_ID: str = ""
    GHL_BOOKING_WIDGET_URL: str = ""
    GHL_WEBHOOK_SECRET: str = ""
    LEAD_PIPELINE_BASE_URL: str = ""
    LEAD_PIPELINE_SERVICE_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    SCRIPT_MODEL: str = ""
    # Cheap, fast model for reading crawled clinic pages (OpenRouter id).
    RESEARCH_MODEL: str = "anthropic/claude-haiku-5.5"
    AI_VISIBILITY_MODELS: str = ""
    FIRECRAWL_API_KEY: str = ""
    GOOGLE_PAGESPEED_API_KEY: str = ""
    APIFY_API_TOKEN: str = ""
    # Apify's Google Maps scraper; override in .env to use another actor.
    APIFY_GMAPS_ACTOR_ID: str = "compass~crawler-google-places"
    APOLLO_API_KEY: str = ""
    AHREFS_API_KEY: str = ""
    REPORT_FROM_EMAIL: str = ""
    SLACK_MARKETING_ALERTS_WEBHOOK: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )


settings = Settings()
