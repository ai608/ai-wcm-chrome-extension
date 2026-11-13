from typing import Any

import pytest

from app.core.config import settings
from app.services import llm, page_types, site_crawl
from tests.test_site_crawl import base_sections, rich

G = "https://glow.example"
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def page(title: str, h1: str, text: str) -> str:
    return f"<html><head><title>{title}</title></head><body><h1>{h1}</h1><p>{text}</p></body></html>"


def test_only_pages_without_a_strong_signal_go_to_the_ai():
    menu = site_crawl.Menu(
        children={
            f"{G}/botox": "Injectables",
            f"{G}/why-botox-is-safe-for-your-face": "About",
        },
        parents={},
        top={
            f"{G}/botox": "botox",
            f"{G}/why-botox-is-safe-for-your-face": "why botox",
        },
    )
    sections = base_sections()
    sections["site"]["services"]["clusters"] = [
        {
            "service": "Neurotoxins",
            "found": 3,
            "expected": 3,
            "topics_present": [],
            "topics_missing": [],
            "pages": [
                f"{G}/botox",
                f"{G}/why-botox-is-safe-for-your-face",
                f"{G}/services/iv",
            ],
        }
    ]
    urls = [
        f"{G}/botox",
        f"{G}/why-botox-is-safe-for-your-face",
        f"{G}/services/iv",
        f"{G}/hormone-pellets",
        f"{G}/privacy-policy",
    ]
    pages = {u: rich(u) for u in urls}
    got = page_types.candidates(sections, urls, pages, menu)
    # a short address in a service dropdown and a services folder are certain; a post filed
    # under About and a page no rule claimed are not
    assert got == [f"{G}/why-botox-is-safe-for-your-face", f"{G}/hormone-pellets"]


def test_the_ais_answer_moves_only_the_pages_it_read():
    sections = base_sections()
    sections["site"]["services"]["clusters"] = [
        {
            "service": "Botox",
            "found": 2,
            "expected": 3,
            "topics_present": [],
            "topics_missing": [],
            "pages": [f"{G}/botox", f"{G}/botox-aftercare-tips"],
        }
    ]
    pages = {
        f"{G}/hormone-pellets": page("Pellets", "Hormone Pellet Therapy", "Book now")
    }
    labels = {
        f"{G}/botox-aftercare-tips": {"label": "blog_post", "service": ""},
        f"{G}/hormone-pellets": {
            "label": "service",
            "service": "Hormone Pellet Therapy",
        },
    }
    page_types.apply(sections, labels, pages)
    by = {c["service"]: c["pages"] for c in sections["site"]["services"]["clusters"]}
    assert by == {
        "Botox": [f"{G}/botox"],
        "Hormone Pellet Therapy": [f"{G}/hormone-pellets"],
    }


async def test_the_reply_is_checked_and_cached_whatever_key_the_model_used(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    calls: list[str] = []

    async def fake(_http: Any, _system: str, user: str, **_k: Any) -> dict[str, Any]:
        calls.append(user)
        return {
            "labels": [  # the schema is not always enforced: another key, odd case
                {"id": "0", "label": "SERVICE", "service": "IV Therapy"},
                {"id": "1", "label": "made_up", "service": ""},
                {"id": "9", "label": "service", "service": "Not a page"},
            ]
        }

    monkeypatch.setattr(llm, "chat_json", fake)
    page_types._CACHE.clear()
    urls = [f"{G}/iv", f"{G}/x"]
    pages = {u: page("IV", "IV Therapy", "Drips") for u in urls}
    got = await page_types.read_types(None, urls, pages)  # type: ignore[arg-type]
    assert got == {f"{G}/iv": {"label": "service", "service": "IV Therapy"}}
    assert await page_types.read_types(None, urls, pages) == got  # type: ignore[arg-type]
    assert len(calls) == 1  # the same pages are not paid for twice


def test_the_ai_sees_the_page_after_its_heading_not_the_menu():
    html = (
        "<html><head><title>Botox</title></head><body><div class='navbar'>About Contact Specials"
        "</div><h1>Botox</h1><p>Smooth lines in 15 minutes.</p></body></html>"
    )
    item = page_types.payload([f"{G}/botox"], {f"{G}/botox": html})[0]
    assert item["opening"].startswith("Smooth lines")
