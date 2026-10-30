from pydantic import Field
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
    # Model that reads the crawled clinic pages (OpenRouter id).
    RESEARCH_MODEL: str = "anthropic/claude-sonnet-5.5"
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

    # Site crawl and AI reading (see site_crawl.crawl). Change them in Railway, no code change;
    # a bad value (0 or negative) stops the app at start-up, not in the middle of an audit.
    # Pages read per audit.
    CRAWL_MAX_PAGES: int = Field(default=40, gt=0)
    # Parallel reads against one clinic server.
    CRAWL_CONCURRENCY: int = Field(default=4, gt=0)
    # Reads stop after this many seconds; finished pages are kept.
    CRAWL_BUDGET_S: float = Field(default=45.0, gt=0)
    # A Firecrawl map slower than this is dropped.
    CRAWL_MAP_TIMEOUT_S: float = Field(default=20.0, gt=0)
    CRAWL_SITEMAP_WAIT_S: float = Field(default=10.0, gt=0)
    # Pages per audit that may use paid Firecrawl after a direct read fails; 0 turns it off.
    FIRECRAWL_FALLBACKS: int = Field(default=10, ge=0)
    # Seconds to wait before the one retry of a failed read (a Retry-After header wins, up to 5).
    CRAWL_RETRY_DELAY_S: float = Field(default=1.0, ge=0)
    # Pages sent to the AI, and the characters of page text across all of them. Measured on
    # clinic pages: about 2.8 characters per token, so 160k characters is about 57k tokens
    # (roughly $0.12 input on Sonnet 5.5). Pages are never cut one by one; when the total runs
    # out, the last pages in reading order are cut, and those are the least important ones.
    AI_MAX_PAGES: int = Field(default=40, gt=0)
    AI_MAX_OUTPUT_TOKENS: int = Field(default=16000, gt=0)
    AI_TOTAL_CHARS: int = Field(default=160_000, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )


settings = Settings()
