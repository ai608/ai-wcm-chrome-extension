from app.services import site_ai, site_audit, site_crawl

HOME = "https://glow.example/"
BOTOX = "https://glow.example/services/botox"
PAGE = "<html><head><title>Botox</title><script>var x=1</script></head><body><h1>Botox in Austin</h1><p>What it is and who it is for.</p></body></html>"


def sections():
    s = site_audit.analyze(
        "<html><head><title>Glow</title></head><body><h1>Glow</h1></body></html>", HOME
    )
    site_crawl.enrich(
        s, [HOME, BOTOX, "https://glow.example/locations/austin"], {BOTOX: PAGE}
    )
    return s


def test_page_text_drops_scripts_and_keeps_headings():
    text = site_ai.page_text(PAGE)
    assert (
        "var x" not in text
        and "Botox in Austin" in text
        and text.startswith("TITLE: Botox")
    )


CHROME_PAGE = (
    "<html><body><header><h1>Glow Med Spa</h1><nav>Botox IV Therapy</nav></header>"
    "<main><article><header><h2>Botox FAQ</h2></header><p>Pricing starts at $12.</p></article></main>"
    "<footer>123 Main St, Austin TX</footer></body></html>"
)


def test_page_text_sends_site_header_and_footer_once():
    _, heads, body = site_ai.page_text(CHROME_PAGE).split("\n", 2)
    assert "Glow Med Spa" in heads  # the H1 inside the header is still sent
    assert "IV Therapy" not in body and "123 Main St" not in body
    assert "Botox FAQ" in body  # an article's own header stays
    chrome = site_ai.site_text(CHROME_PAGE)
    assert chrome.startswith("HEADER: Glow Med Spa Botox IV Therapy")
    assert "FOOTER: 123 Main St" in chrome and "Botox FAQ" not in chrome


def test_apply_merges_topics_areas_providers_and_drops_junk():
    s = sections()
    ai = {
        "services": [
            {
                "service": "Neurotoxins",
                "page_url": BOTOX,
                "topics_present": ["What it is", "Who it is for", "Made up topic"],
            },
            {"service": "Not a real service", "topics_present": ["What it is"]},
            {
                "service": "IV Therapy",
                "page_url": "https://elsewhere.example/iv",
                "topics_present": ["FAQs"],
            },
        ],
        "providers": [
            {"name": "Dr. Jane Doe", "credentials": "MD"},
            {"credentials": "RN"},
        ],
        "areas_served": ["Austin", "Round Rock"],
        "offers": ["20% off first visit"],
        "financing": True,
        "insurance_accepted": False,
    }
    site_ai.apply(s, ai, {BOTOX: PAGE})
    clusters = {c["service"]: c for c in s["site"]["services"]["clusters"]}
    botox = clusters["Neurotoxins"]
    assert botox["topics_present"] == ["What it is", "Who it is for"]
    assert (
        "Made up topic" not in botox["topics_missing"]
        and "FAQs" in botox["topics_missing"]
    )
    assert "Not a real service" not in clusters
    assert (
        clusters["IV Therapy"]["pages"] == []
    )  # URL not from this site is not trusted
    assert s["site"]["cities"]["claimed_not_built"] == ["Round Rock"]
    trust = {t["key"]: t["status"] for t in s["site"]["trust"]}
    assert (
        trust["provider_credentials"] == "found"
        and trust["insurance_info"] == "missing"
    )
    assert (
        s["convert"]["financing_mentioned"] is True
        and s["convert"]["offers_or_specials"] is True
    )
    assert s["site"]["ai"]["providers"] == [
        {"name": "Dr. Jane Doe", "credentials": "MD"}
    ]


def test_apply_tolerates_garbage():
    s = sections()
    site_ai.apply(
        s, {"services": "nope", "providers": [1, None], "areas_served": None}, {}
    )
    assert s["site"]["cities"]["claimed_not_built"] == []


def test_headings_keep_the_space_a_line_break_stood_for():
    html = "<html><body><h1>Bio-Identical<br>Hormone Therapy</h1><h2>Family<br/>Planning</h2></body></html>"
    assert (
        "HEADINGS: Bio-Identical Hormone Therapy | Family Planning"
        in site_ai.page_text(html)
    )


def test_page_text_is_not_cut_and_analyze_keeps_pages_whole_until_the_budget_ends(
    monkeypatch,
):
    import asyncio

    long_page = (
        "<html><body><main><p>"
        + "pricing and faq. " * 1000
        + "</p></main></body></html>"
    )
    assert len(site_ai.page_text(long_page)) > 17_000  # the old 2,500 cut is gone
    seen = {}

    async def chat(_http, _system, user, **kw):
        seen["user"], seen["max_tokens"] = user, kw["max_tokens"]
        return {}

    monkeypatch.setattr(site_ai.llm, "chat_json", chat)
    monkeypatch.setattr(site_ai.settings, "AI_TOTAL_CHARS", 30_000)
    pages = {f"https://g.example/p{i}": long_page for i in range(5)}
    asyncio.run(site_ai.analyze(None, pages))
    user = seen["user"]
    assert (
        user.count("=== PAGE") == 2
    )  # p0 whole, p1 cut to what is left; p2.. left out
    assert "=== PAGE https://g.example/p0" in user and "p2" not in user
    assert len(user) < 30_000 + 400 and seen["max_tokens"] == 6000


def test_a_json_reply_in_a_code_fence_is_read_and_a_cut_off_one_is_named():
    import pytest

    from app.core.exceptions import AppError
    from app.services import llm

    assert llm.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_object('{"a": 1}') == {"a": 1}
    with pytest.raises(TypeError):
        llm.parse_json_object("[1]")
    with pytest.raises(ValueError):
        llm.parse_json_object("")

    def reply(content, finish):
        import httpx

        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": content}, "finish_reason": finish}
                        ]
                    },
                )
            )
        )

    async def call(content, finish):
        async with reply(content, finish) as http:
            return await llm.chat_json(http, "s", "u", model="m")

    import asyncio

    llm.settings.OPENROUTER_API_KEY = "k"
    try:
        assert asyncio.run(call('```json\n{"a": 1}\n```', "stop")) == {"a": 1}
        with pytest.raises(AppError, match="cut off"):
            asyncio.run(call('{"a": [1,', "length"))
        with pytest.raises(AppError, match="invalid JSON"):
            asyncio.run(call("sorry, no", "stop"))
    finally:
        llm.settings.OPENROUTER_API_KEY = ""
