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
