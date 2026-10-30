from datetime import UTC, datetime
from typing import Any

import pytest

from app.services import site_score

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def good() -> dict[str, Any]:
    """A clinic that does everything right."""
    return {
        "business": {
            "gbp": {
                "matched": True,
                "verified": True,
                "primary_category": "Medical spa",
                "rating": 4.8,
                "review_count": 240,
                "website_links_to_gbp": True,
                "review_link_on_site": True,
            },
            "nap": {"consistent_with_gbp": True},
            "socials": [{"network": n, "url": "x"} for n in ("fb", "ig", "yt")],
        },
        "on_page": {
            "essentials": [{"key": "title", "label": "Page title", "status": "ok"}],
            "pagespeed": {"mobile_performance": 95},
        },
        "schema": {"has_local_business": True, "parse_errors": 0},
        "site": {
            "services": {
                "clusters": [
                    {
                        "service": "Neurotoxins",
                        "found": 3,
                        "expected": 3,
                        "topics_present": list("abcdefghi"),
                        "topics_missing": [],
                    }
                ]
            },
            "cities": {"pages_found": 6, "hub_page": True, "claimed_not_built": []},
            "proof": {
                "before_after_gallery": True,
                "testimonial_pages": 1,
                "reviews_page": True,
                "case_study_pages": 2,
                "video_testimonials": True,
            },
            "trust": [{"key": "provider_credentials", "status": "found"}],
            "blog": {
                "post_count": 30,
                "last_post_at": "2026-09-15",
                "posts_last12_months": 8,
                "links_to_services": True,
            },
        },
        "convert": {
            "online_booking": True,
            "phone_in_header": True,
            "click_to_call": True,
            "forms_count": 1,
            "chat_widget": "Podium",
            "cta_above_fold": True,
            "checks": [
                {"key": "online_booking", "status": "ok"},
                {"key": "click_to_call", "status": "ok"},
                {"key": "contact_form", "status": "ok"},
            ],
        },
    }


def run(sections: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return site_score.compute(sections, now=NOW, **kw)


def cat(result: dict[str, Any], key: str) -> dict[str, Any]:
    return next(c for c in result["categories"] if c["key"] == key)


def test_all_good_clinic_gets_an_a() -> None:
    out = run(good(), pagespeed_ok=True, domain="glow.example")
    assert out["score"] == 100 and out["grade"] == "A"
    assert out["provisional"] is False and out["provisional_reasons"] == []
    assert [c["key"] for c in out["categories"]] == [
        k for k, _, _ in site_score.CATEGORIES
    ]
    assert sum(c["weight"] for c in out["categories"]) == 100
    assert all(c["score"] == 100 and not c["excluded"] for c in out["categories"])
    assert out["top_issues"] == [] and out["issue_count"] == 0
    assert out["summary_text"].startswith("glow.example: 100/100 (A).")


def test_gbp_points() -> None:
    s = good()
    s["business"]["gbp"].update(verified=False, primary_category=None)
    assert cat(run(s), "google_business_profile")["score"] == 70
    s["business"]["gbp"]["website_links_to_gbp"] = False
    s["business"]["nap"]["consistent_with_gbp"] = None  # unknown: no points, no issue
    out = run(s)
    assert cat(out, "google_business_profile")["score"] == 40
    titles = [i["title"] for i in out["top_issues"]]
    assert "Google profile is not claimed" in titles
    assert "Phone number differs from the Google profile" not in titles


def test_reviews_tiers() -> None:
    s = good()
    gbp = s["business"]["gbp"]
    gbp.update(rating=4.2, review_count=40)
    assert cat(run(s), "reviews")["score"] == 25 + 25 + 20
    gbp.update(rating=3.9, review_count=None, review_link_on_site=False)
    assert cat(run(s), "reviews")["score"] == 0
    gbp.update(rating=4.5, review_count=100)
    assert cat(run(s), "reviews")["score"] == 80


def test_no_gbp_excludes_gbp_and_reviews_and_rescales() -> None:
    s = good()
    s["business"]["gbp"] = None
    s["convert"].update(
        checks=[], forms_count=0, chat_widget=None, cta_above_fold=False
    )
    out = run(s, pagespeed_ok=True)
    for key in ("google_business_profile", "reviews"):
        c = cat(out, key)
        assert c["excluded"] is True and c["score"] is None and c["grade"] is None
    assert cat(out, "getting_the_call")["score"] == 50  # 3 of 6
    # Worked example: included weights 75. Getting the call 50, everything else 100:
    # (15*100 + 10*100 + 15*50 + 10*100 + 10*100 + 10*100 + 5*100) / 75 = 6750 / 75 = 90.
    # Without rescaling it would be 67.5.
    assert out["score"] == 90 and out["grade"] == "A"
    assert out["provisional"] is True
    assert out["provisional_reasons"] == [site_score.NO_GBP]
    # points lost are on the rescaled 100-point total: 15/75*100 * 50% = 10
    assert cat(out, "getting_the_call")["points_lost"] == 10.0


def test_unmatched_gbp_is_excluded_too() -> None:
    s = good()
    s["business"]["gbp"]["matched"] = False
    assert cat(run(s), "reviews")["excluded"] is True


def test_service_pages_mix_coverage_and_topics() -> None:
    s = good()
    s["site"]["services"]["clusters"] = [
        # 2/4 pages, 3/9 topics: 0.5*0.5 + 0.5*(3/9) = 0.4167
        {
            "service": "A",
            "found": 2,
            "expected": 4,
            "topics_present": ["x"] * 3,
            "topics_missing": ["y"],
        },
        {
            "service": "B",
            "found": 5,
            "expected": 3,
            "topics_present": [],
            "topics_missing": [],
        },
    ]
    out = run(s)
    assert cat(out, "service_pages")["score"] == 42
    assert out["top_issues"][0]["title"] == "A pages are thin"
    for c in s["site"]["services"]["clusters"]:
        c["topics_present"] = c["topics_missing"] = []
    assert (
        cat(run(s), "service_pages")["score"] == 75
    )  # no topics anywhere: coverage only
    s["site"]["services"]["clusters"] = []
    assert cat(run(s), "service_pages")["score"] == 0


def test_service_area_pages_hub_and_penalty() -> None:
    s = good()
    cities = s["site"]["cities"]
    cities.update(pages_found=2, hub_page=False)
    assert cat(run(s), "service_area")["score"] == 28  # 70 * 2/5
    cities.update(pages_found=5, hub_page=True, claimed_not_built=["a", "b"])
    assert cat(run(s), "service_area")["score"] == 80
    cities.update(pages_found=0, hub_page=False, claimed_not_built=list("abcdef"))
    assert cat(run(s), "service_area")["score"] == 0  # floor, penalty capped at 30


def test_getting_the_call_prefers_check_status() -> None:
    s = good()
    s["convert"]["checks"][0]["status"] = "warn"  # online booking: 0.5 despite True
    s["convert"]["chat_widget"] = None
    out = run(s)
    assert cat(out, "getting_the_call")["score"] == 75  # 4.5 / 6
    titles = [i["title"] for i in out["top_issues"]]
    assert "No online booking found" in titles and "No live chat on the site" in titles
    assert out["warning_count"] == 1
    assert out["issue_count"] == 1  # the chat miss; the warn check is a warning


def test_site_fundamentals_parts_and_missing_pagespeed() -> None:
    s = good()
    s["on_page"]["essentials"].append({"key": "h1", "status": "warn"})
    s["schema"]["has_local_business"] = False
    s["on_page"]["pagespeed"]["mobile_performance"] = 60
    # 0.6*0.75 + 0.15*0.5 + 0.25*0.5 = 0.65
    assert cat(run(s, pagespeed_ok=True), "site_fundamentals")["score"] == 65
    s["on_page"]["pagespeed"] = None
    out = run(s, pagespeed_ok=False)
    # speed dropped and rescaled: (0.6*0.75 + 0.15*0.5) / 0.75 = 0.7
    assert cat(out, "site_fundamentals")["score"] == 70
    assert out["provisional"] is True
    assert out["provisional_reasons"] == [site_score.NO_PAGESPEED]
    # not run at all (no key) is also unavailable
    assert run(s, pagespeed_ok=None)["provisional_reasons"] == [site_score.NO_PAGESPEED]


def test_content_and_proof_share() -> None:
    s = good()
    s["site"]["proof"].update(video_testimonials=False, case_study_pages=0)
    s["site"]["trust"] = [{"key": "provider_credentials", "status": "missing"}]
    assert cat(run(s), "content_and_proof")["score"] == 50


def test_supporting_content_age_volume_links() -> None:
    s = good()
    blog = s["site"]["blog"]
    blog.update(last_post_at="2026-05-01", posts_last12_months=3)  # 153 days old
    assert cat(run(s), "supporting_content")["score"] == 20 + 20 + 20
    blog.update(last_post_at="2025-01-01", links_to_services=False)
    assert cat(run(s), "supporting_content")["score"] == 20
    blog.update(last_post_at=None, posts_last12_months=0, post_count=0)
    out = run(s)
    assert cat(out, "supporting_content")["score"] == 0
    titles = [i["title"] for i in out["top_issues"]]
    assert "No blog posts found" in titles
    assert "Blog posts do not link to treatment pages" not in titles


def test_supporting_content_does_not_punish_dates_it_never_found() -> None:
    s = good()
    # 80 posts, only 2 with a date: the counts are minimums, so no "only 1 post" issue
    s["site"]["blog"].update(
        post_count=80, dated_posts=2, last_post_at="2025-07-11", posts_last12_months=1
    )
    titles = [
        i["title"]
        for i in run(s)["top_issues"]
        if i["category"] == "supporting_content"
    ]
    assert not any("blog post" in t.lower() for t in titles)
    # the same numbers with the dates known are a real finding
    s["site"]["blog"].update(dated_posts=80)
    titles = [
        i["title"]
        for i in run(s)["top_issues"]
        if i["category"] == "supporting_content"
    ]
    assert any("blog post" in t.lower() for t in titles)


def test_social_and_video() -> None:
    s = good()
    s["business"]["socials"] = s["business"]["socials"][:1]
    s["site"]["proof"]["video_testimonials"] = False
    assert cat(run(s), "social_and_video")["score"] == 23  # 70 / 3


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (100, "A"),
        (90, "A"),
        (89, "B"),
        (75, "B"),
        (74, "C"),
        (60, "C"),
        (59, "D"),
        (45, "D"),
        (44, "F"),
        (0, "F"),
    ],
)
def test_grade_band_edges(score: int, grade: str) -> None:
    assert site_score.grade_for(score) == grade


def test_top_issues_ranked_by_weight_times_loss() -> None:
    s = good()
    # service area (weight 10) loses 70 -> 700; social (weight 5) loses 70 -> 350;
    # getting the call (weight 15) loses 17 -> 255.
    s["business"]["socials"] = []
    s["site"]["cities"].update(pages_found=0, hub_page=True)
    s["convert"]["phone_in_header"] = False
    out = run(s)
    order = list(dict.fromkeys(i["category"] for i in out["top_issues"]))
    assert order == ["service_area", "social_and_video", "getting_the_call"]
    assert len(out["top_issues"]) <= site_score.MAX_TOP_ISSUES
    assert all(
        i["category"] in {k for k, _, _ in site_score.CATEGORIES}
        for i in out["top_issues"]
    )


def test_no_categories_is_safe() -> None:
    out = run({})
    assert out["score"] is None and out["grade"] is None
    assert out["provisional"] is True
    assert all(c["excluded"] for c in out["categories"])
    assert out["top_issues"] == [] and out["issue_count"] == 0
    assert "not enough data" in out["summary_text"]


def test_placeholder_text_is_a_top_issue_without_changing_the_score() -> None:
    s = good()
    before = run(s)["score"]
    s["site"]["placeholder_pages"] = ["https://clinic.example/about/"]
    out = run(s)
    assert out["score"] == before
    assert any("placeholder" in i["title"].lower() for i in out["top_issues"])
