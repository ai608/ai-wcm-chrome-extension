import pytest

from app.core.config import settings

# Tests must never touch the real database or paid providers configured in .env.
# Individual tests opt back in with their own fakes (e.g. GHL via MockTransport).
_LIVE = (
    "DATABASE_URL",
    "GHL_PIT",
    "FIRECRAWL_API_KEY",
    "APIFY_API_TOKEN",
    "OPENROUTER_API_KEY",
    "AHREFS_API_KEY",
    "APOLLO_API_KEY",
    "GOOGLE_PAGESPEED_API_KEY",
    "SLACK_MARKETING_ALERTS_WEBHOOK",
)


@pytest.fixture(autouse=True)
def _no_live_services(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _LIVE:
        monkeypatch.setattr(settings, key, "")
