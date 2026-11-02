from app.services import onpage, site_audit, site_crawl

G = "https://glow.example"
LONG = " ".join(f"word{i}" for i in range(200))


def page(
    title="Botox in Austin | Glow",
    h1="<h1>Botox in Austin</h1>",
    head="",
    body=LONG,
):
    return f"<html><head><title>{title}</title>{head}</head><body>{h1}<p>{body}</p></body></html>"


def keys(result):
    return {i["key"] for i in result["issues"]}


def test_a_good_service_page_has_no_issues_beyond_a_missing_description():
    r = onpage.analyze_page(
        page(head=f'<link rel="canonical" href="{G}/botox">'), f"{G}/botox", "service"
    )
    assert keys(r) == {"no_description"} and r["word_count"] >= 200


def test_missing_title_h1_noindex_and_thin_text_on_a_service_page():
    html = page(
        title="",
        h1="",
        head='<meta name="robots" content="noindex,follow">',
        body="short",
    )
    r = onpage.analyze_page(html, f"{G}/botox", "service")
    assert {"no_title", "no_h1", "noindex", "thin_page", "canonical_missing"} <= keys(r)
    sev = {i["key"]: i["severity"] for i in r["issues"]}
    assert sev["noindex"] == "critical" and sev["no_h1"] == "high"


def test_the_same_problem_on_a_minor_page_is_milder():
    html = page(h1="", head='<meta name="robots" content="noindex">')
    r = onpage.analyze_page(html, f"{G}/contact", "other")
    sev = {i["key"]: i["severity"] for i in r["issues"]}
    assert sev["noindex"] == "low" and sev["no_h1"] == "low"
    assert "no_description" not in sev


def test_canonical_problems_are_told_apart():
    def status(href):
        head = f'<link rel="canonical" href="{href}">'
        return onpage.analyze_page(page(head=head), f"{G}/botox", "service")[
            "canonical"
        ]["status"]

    assert status(f"{G}/botox/") == "ok"
    assert status("https://www.glow.example/botox") == "ok"
    assert status("/botox") == "relative"
    assert status(f"{G}/other") == "other_page"
    assert status("https://elsewhere.example/botox") == "other_host"
    assert status(f"{G}/botox#top") == "fragment"


def test_generic_old_year_and_unrelated_titles():
    r = onpage.analyze_page(page(title="Home"), f"{G}/", "home")
    assert "generic_title" in keys(r)
    r = onpage.analyze_page(
        page(title="Best deals in 2019 | Glow"), f"{G}/botox", "service"
    )
    assert {"old_year_title", "title_no_topic"} <= keys(r)


def test_a_page_with_almost_no_text_but_a_big_source_is_js_only():
    big = "<script>" + "x" * 150_000 + "</script>"
    r = onpage.analyze_page(page(body="hi") + big, f"{G}/botox", "service")
    assert "js_only" in keys(r)


def test_duplicate_titles_and_text_are_found_and_flagged_on_each_page():
    a = onpage.analyze_page(page(title="Treatments | Glow"), f"{G}/a-botox", "service")
    b = onpage.analyze_page(page(title="Treatments | Glow"), f"{G}/b-botox", "service")
    c = onpage.analyze_page(
        page(title="Other | Glow", body="different " * 200), f"{G}/c-botox", "service"
    )
    pages = [a, b, c]
    dups = onpage._duplicates(pages)
    assert dups["titles"] == [[f"{G}/a-botox", f"{G}/b-botox"]]
    assert dups["text"] == [[f"{G}/a-botox", f"{G}/b-botox"]]
    onpage._add_duplicate_issues(pages, dups)
    assert "duplicate_title" in keys(a) and "duplicate_text" in keys(b)
    assert "duplicate_title" not in keys(c)


def sections_for(ld):
    html = (
        f'<html><head><title>Glow</title><script type="application/ld+json">{ld}</script></head>'
        "<body><h1>Glow</h1></body></html>"
    )
    return site_audit.analyze(html, f"{G}/"), html


def test_schema_checks_list_missing_properties_and_the_review_risk():
    ld = (
        '{"@type":"LocalBusiness","name":"Glow","telephone":"512-555-0000",'
        '"aggregateRating":{"@type":"AggregateRating","ratingValue":5,"reviewCount":9}}'
    )
    sections, html = sections_for(ld)
    issues = {i["key"]: i for i in onpage.schema_checks(sections, html)}
    assert "address" in issues["schema_missing_required"]["title"]
    assert "geo" in issues["schema_missing_recommended"]["title"]
    assert {"schema_generic_type", "schema_self_serving_review"} <= set(issues)
    assert sections["schema"]["risks"] == ["self_serving_review"]
    block = sections["schema"]["blocks"][0]
    assert block["missing_required"] == ["address"]


def test_a_complete_specific_business_block_raises_no_schema_issue():
    ld = (
        '{"@type":"MedicalClinic","name":"Glow","address":"1 Main St","telephone":"512-555-0000",'
        '"url":"https://glow.example","geo":{"@type":"GeoCoordinates"},'
        '"openingHoursSpecification":[{"opens":"09:00"}],"priceRange":"$$","image":"a.jpg"}'
    )
    sections, html = sections_for(ld)
    assert onpage.schema_checks(sections, html) == []
    assert sections["schema"]["local_business_type"] == "MedicalClinic"


HOME = """<html><head><title>Glow Med Spa Austin</title></head><body><h1>Glow</h1>
<a href="/botox">Learn more</a><a href="/iv">Learn more</a><a href="/peels">click here</a>
<a href="/x"></a><a href="javascript:void(0)">Open</a><a onclick="go()">No link</a><a href="#">Menu</a>
<img src="/img/IMG_0023.jpg" width="800" alt="image" loading="lazy">
<p>Provider: Dr. Jane Doe, MD. Medically reviewed by Dr. Doe. Results may vary.
Updated: March 3, 2026. See <a href="https://www.nih.gov/x">NIH</a>.</p></body></html>"""


def test_home_checks_find_anchors_images_trust_and_missing_local_facts():
    sections = site_audit.analyze(HOME, f"{G}/")
    onpage.run(
        sections,
        f"{G}/",
        {f"{G}/": HOME},
        [
            f"{G}/",
            f"{G}/botox",
            f"{G}/services/hidden-botox",
            f"{G}/what-to-expect-with-botox",
        ],
        site_crawl.Menu({}, {}, {f"{G}/botox": "botox"}),
    )
    on_page = sections["on_page"]
    assert on_page["links"]["generic_anchor_count"] == 3
    assert on_page["links"]["empty_anchor_count"] == 1
    assert on_page["links"]["not_crawlable_count"] == 2
    assert on_page["images"]["first_image_lazy"] and on_page["images"]["bad_alt"] == 1
    trust = on_page["trust"]
    assert trust["credentials_pages"] == [f"{G}/"] and trust["reference_links"] == 1
    assert (
        trust["reviewed_by_pages"]
        and trust["dated_pages"]
        and trust["disclaimer_pages"]
    )
    assert on_page["orphans"] == [f"{G}/services/hidden-botox"]
    keys_ = {i["key"] for i in on_page["site_issues"]}
    assert {
        "anchors_generic",
        "images_lazy_first",
        "orphan_pages",
        "local_no_map",
    } <= keys_
    assert "trust_no_credentials" not in keys_
    assert [p["kind"] for p in on_page["pages"]] == ["home"]


def test_summary_scores_by_severity_and_lists_only_real_fixes():
    issues = [
        {
            "key": "noindex",
            "severity": "critical",
            "title": "t",
            "detail": "d",
            "url": "u1",
        },
        {
            "key": "noindex",
            "severity": "critical",
            "title": "t",
            "detail": "d",
            "url": "u2",
        },
        {"key": "no_h1", "severity": "high", "title": "t", "detail": "d", "url": "u3"},
        {
            "key": "no_description",
            "severity": "low",
            "title": "t",
            "detail": "d",
            "url": "u4",
        },
    ]
    s = onpage._summary(issues)
    assert s["score"] == 100 - 30 - 6 and s["critical"] == 2 and s["low"] == 1
    assert [f["key"] for f in s["top_fixes"]] == ["noindex", "no_h1"]
    assert s["top_fixes"][0]["count"] == 2 and s["top_fixes"][0]["pages"] == [
        "u1",
        "u2",
    ]


def test_the_score_counts_one_issue_at_most_three_times():
    issues = [
        {
            "key": "no_h1",
            "severity": "high",
            "title": "t",
            "detail": "d",
            "url": f"u{i}",
        }
        for i in range(9)
    ]
    assert onpage._summary(issues)["score"] == 100 - 6 * 2


def test_a_business_described_across_two_blocks_is_judged_as_one():
    ld = (
        '[{"@type":["MedicalClinic","Organization"],"name":"Glow","url":"https://glow.example"},'
        '{"@type":"MedicalBusiness","name":"Glow","address":"1 Main St","telephone":"512-555-0000",'
        '"openingHoursSpecification":[{"opens":"09:00"}]}]'
    )
    sections, html = sections_for(ld)
    issues = {i["key"]: i for i in onpage.schema_checks(sections, html)}
    assert "schema_missing_required" not in issues
    assert "geo" in issues["schema_missing_recommended"]["title"]
    assert "telephone" not in issues["schema_missing_recommended"]["title"]
