from app.services import constants as c


def test_markers_are_written_the_way_they_are_matched():
    # BOOKING/CHAT are looked up in lower-cased HTML and SERVICES in lower-cased URLs and
    # text: an upper-case entry would never match, and nothing would say so.
    for table in (c.BOOKING, c.CHAT):
        assert all(k == k.lower() for k in table)
    assert all(t == t.lower() for terms in c.SERVICES.values() for t in terms)
    assert all(t.strip() for terms in c.SERVICES.values() for t in terms)


def test_a_bad_crawl_setting_stops_the_app_at_start_up():
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(CRAWL_MAX_PAGES=0)
    with pytest.raises(ValidationError):
        Settings(CRAWL_BUDGET_S=-1)
    assert (
        Settings(FIRECRAWL_FALLBACKS=0).FIRECRAWL_FALLBACKS == 0
    )  # 0 turns fallbacks off
