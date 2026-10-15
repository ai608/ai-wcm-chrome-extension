from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "local"
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    ENCRYPTION_KEY: str = ""
    FULL_ACCESS_EMAILS: str = "raj.gajjar@e2m.solutions"
    CORS_ALLOWED_ORIGINS: str = ""
    GHL_PIT: str = ""
    GHL_SALES_LOCATION_ID: str = ""
    GHL_BOOKING_WIDGET_URL: str = ""
    GHL_WEBHOOK_SECRET: str = ""
    LEAD_PIPELINE_BASE_URL: str = ""
    LEAD_PIPELINE_SERVICE_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    SCRIPT_MODEL: str = ""
    AI_VISIBILITY_MODELS: str = ""
    FIRECRAWL_API_KEY: str = ""
    GOOGLE_PAGESPEED_API_KEY: str = ""
    APIFY_API_TOKEN: str = ""
    APIFY_GMAPS_ACTOR_ID: str = ""
    APOLLO_API_KEY: str = ""
    AHREFS_API_KEY: str = ""
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    REPORT_FROM_EMAIL: str = ""
    SLACK_MARKETING_ALERTS_WEBHOOK: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )


settings = Settings()
