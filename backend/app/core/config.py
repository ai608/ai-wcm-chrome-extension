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
    # "Label=openrouter/model-id" pairs, comma separated, e.g.
    # "ChatGPT=openai/gpt-4o-mini,Gemini=google/gemini-2.5-flash,Perplexity=perplexity/sonar".
    # Empty turns AI visibility off.
    AI_VISIBILITY_MODELS: str = ""
    # The judge: reads every AI answer and decides who was named, rank, position, link and
    # sentiment (one call per answer). Also writes the report's questions and, when there are no
    # local competitors, lists the businesses the answers name. Cheap is fine, but a weaker model
    # misreads names more often. Empty uses SCRIPT_MODEL.
    AI_VISIBILITY_JUDGE_MODEL: str = ""
    # What one user's runs may cost in 24 hours. The next run is refused past this.
    AI_VISIBILITY_DAILY_BUDGET_USD: float = Field(default=5.0, gt=0)
    # Full report size. Calls = prompts x engines x repeats (plus one judge call per answer).
    AI_VISIBILITY_FULL_PROMPTS: int = Field(default=12, ge=1, le=100)
    AI_VISIBILITY_FULL_RUNS: int = Field(default=2, ge=1, le=5)
    # A run that would make more answer calls than this is refused at start (typo guard).
    AI_VISIBILITY_FULL_MAX_CALLS: int = Field(default=400, gt=0)
    # One full run stops asking once it has spent this much; the result is then "partial".
    AI_VISIBILITY_FULL_RUN_BUDGET_USD: float = Field(default=3.0, gt=0)
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
    CRAWL_MAX_PAGES: int = Field(default=60, gt=0)
    # Parallel reads against one clinic server.
    CRAWL_CONCURRENCY: int = Field(default=4, gt=0)
    # Reads stop after this many seconds; finished pages are kept.
    CRAWL_BUDGET_S: float = Field(default=60.0, gt=0)
    # A Firecrawl map slower than this is dropped.
    CRAWL_MAP_TIMEOUT_S: float = Field(default=20.0, gt=0)
    CRAWL_SITEMAP_WAIT_S: float = Field(default=10.0, gt=0)
    # Pages per audit that may use paid Firecrawl after a direct read fails; 0 turns it off.
    FIRECRAWL_FALLBACKS: int = Field(default=10, ge=0)
    # Seconds to wait before the one retry of a failed read (a Retry-After header wins, up to 5).
    CRAWL_RETRY_DELAY_S: float = Field(default=1.0, ge=0)
    # A site that blocks direct reads is read through Firecrawl: at most this many pages, this
    # many at a time (Firecrawl limits requests per minute), and a Retry-After up to this many
    # seconds is waited for. A longer one is not: that page is reported as rate limited.
    FIRECRAWL_MAX_PAGES: int = Field(default=30, gt=0)
    FIRECRAWL_CONCURRENCY: int = Field(default=2, gt=0)
    FIRECRAWL_MAX_WAIT_S: float = Field(default=30.0, ge=0)
    # Pages sent to the AI, and the characters of page text across all of them. Measured on
    # clinic pages: about 2.8 characters per token, so 200k characters is about 71k tokens
    # (roughly $0.15 input on Sonnet 5.5). Pages are never cut one by one; when the total runs
    # out, the last pages in reading order are cut, and those are the least important ones.
    AI_MAX_PAGES: int = Field(default=60, gt=0)
    AI_MAX_OUTPUT_TOKENS: int = Field(default=16000, gt=0)
    AI_TOTAL_CHARS: int = Field(default=200_000, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )


settings = Settings()
