import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.services import site_crawl

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

    # The post-sitemap lookup fetches the clinic site directly; keep it offline.
    async def offline(*_args: object, **_kwargs: object) -> tuple[str, str]:
        raise AppError(422, "site_unreachable", "offline in tests")

    monkeypatch.setattr(site_crawl, "fetch_html", offline)
