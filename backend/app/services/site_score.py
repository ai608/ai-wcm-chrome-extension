"""Final weighted website score (TDD section 5). Pure: no network, no database.

Runs once, after the whole audit (crawl, AI, GBP, PageSpeed) has finished. Every number a
sales lead may want to tune is a module-level constant below.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from app.services.site_audit import ISSUE_COPY

# (key, label, weight). Weights add up to 100; missing categories are rescaled away.
CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("google_business_profile", "Google Business Profile", 15),
    ("reviews", "Reviews", 10),
    ("service_pages", "Service pages", 15),
    ("service_area", "Service area", 10),
    ("getting_the_call", "Getting the call", 15),
    ("site_fundamentals", "Site fundamentals", 10),
    ("content_and_proof", "Content and proof", 10),
    ("supporting_content", "Supporting content", 10),
    ("social_and_video", "Social and video", 5),
)

# Grade bands (TDD): lowest score that earns each letter.
GRADE_A = 90
GRADE_B = 75
GRADE_C = 60
GRADE_D = 45

# Google Business Profile: points per item (adds up to 100).
GBP_MATCHED = 40  # a profile was found for this website
GBP_VERIFIED = 20  # the owner has claimed the profile
GBP_PRIMARY_CATEGORY = 10  # a primary category is set
GBP_WEBSITE_LINKS = 15  # the website links to the profile
GBP_PHONE_MATCHES = 15  # website phone equals the profile phone

# Reviews: rating and count tiers, plus the review link.
REVIEWS_RATING_TOP = 4.5  # rating at or above this earns the full rating points
REVIEWS_RATING_TOP_POINTS = 40
REVIEWS_RATING_OK = 4.0  # rating at or above this earns the partial rating points
REVIEWS_RATING_OK_POINTS = 25
REVIEWS_COUNT_TOP = 100  # this many reviews earns the full count points
REVIEWS_COUNT_TOP_POINTS = 40
REVIEWS_COUNT_OK = 25  # this many reviews earns the partial count points
REVIEWS_COUNT_OK_POINTS = 25
REVIEWS_LINK = 20  # a "leave a review" link on the site

# Service pages: number of patient topics a full service page covers (site_ai.TOPICS).
SERVICE_TOPICS = 9
SERVICE_COVERAGE_SHARE = 0.5  # share of a service's score from pages found vs expected

# Service area.
AREA_CITY_PAGES_FULL = 5  # this many city pages earns all the city points
AREA_CITY_POINTS = 70
AREA_HUB_POINTS = 30  # a locations hub page
AREA_UNBUILT_PENALTY = 10  # per area the site says it serves but has no page for
AREA_UNBUILT_MAX_PENALTY = 30

# Site fundamentals: share of each part (rescaled when PageSpeed is missing).
FUNDAMENTALS_ESSENTIALS = 0.60
FUNDAMENTALS_SCHEMA = 0.15
FUNDAMENTALS_SPEED = 0.25
SPEED_GOOD = 90  # mobile performance at or above this scores 100
SPEED_OK = 50  # at or above this scores SPEED_OK_SCORE, below scores 0
SPEED_OK_SCORE = 50

# Supporting content (blog).
BLOG_FRESH_DAYS = 90  # latest post this recent earns BLOG_FRESH_POINTS
BLOG_FRESH_POINTS = 40
BLOG_RECENT_DAYS = 180  # latest post this recent earns BLOG_RECENT_POINTS
BLOG_RECENT_POINTS = 20
BLOG_POSTS_YEAR_FULL = 6  # posts in the last 12 months for the full volume points
BLOG_VOLUME_POINTS = 40
BLOG_LINKS_POINTS = 20  # posts link to service pages
BLOG_DATES_MIN_SHARE = (
    0.5  # below this share of dated posts, recency issues are not reported
)

# Social and video.
SOCIAL_PROFILES_FULL = 3  # this many linked social profiles earns all the social points
SOCIAL_POINTS = 70
SOCIAL_VIDEO_POINTS = 30

# Top issues: at most this many per category, and overall.
ISSUES_PER_CATEGORY = 3
MAX_TOP_ISSUES = 10

NO_GBP = "No Google Business Profile found"
NO_PAGESPEED = "PageSpeed unavailable"

_LABEL = {key: label for key, label, _ in CATEGORIES}
_WEIGHT = {key: weight for key, _, weight in CATEGORIES}

# Plain-language copy for misses that are not home-page checks. No em dashes.
MISS_COPY: dict[str, tuple[str, str]] = {
    "gbp_unverified": (
        "Google profile is not claimed",
        "An unclaimed profile can be edited by anyone and ranks lower in the map results.",
    ),
    "gbp_category": (
        "Google profile has no main category",
        "Without a category, Google does not know which treatment searches to show it for.",
    ),
    "gbp_link": (
        "Website does not link to the Google profile",
        "Linking the two helps Google trust that they belong to the same clinic.",
    ),
    "gbp_phone": (
        "Phone number differs from the Google profile",
        "Mismatched numbers confuse Google and send some callers to the wrong line.",
    ),
    "review_link": (
        "No review link on the website",
        "Happy patients have no easy way to leave a Google review.",
    ),
    "placeholder_text": (
        "Template placeholder text is live on the site",
        "Visitors see filler such as Lorem Ipsum, which makes the clinic look unfinished.",
    ),
    "no_services": (
        "No treatment pages found",
        "Patients searching for a treatment never land on this site.",
    ),
    "no_city_pages": (
        "No city or service area pages",
        "Patients in nearby towns cannot find a page built for their search.",
    ),
    "no_hub": (
        "No locations page",
        "There is no single page listing every area the clinic serves.",
    ),
    "phone_in_header": (
        "Phone number is not in the header",
        "Visitors have to hunt for the number before they can call.",
    ),
    "chat_widget": (
        "No live chat on the site",
        "Visitors with a quick question leave instead of starting a conversation.",
    ),
    "no_local_business": (
        "No LocalBusiness schema",
        "Google gets no structured signal for the clinic name, address and hours.",
    ),
    "schema_errors": (
        "Structured data has errors",
        "Google ignores schema it cannot read.",
    ),
    "before_after_gallery": (
        "No before and after gallery",
        "Patients choosing an elective treatment want to see real results first.",
    ),
    "testimonial_pages": (
        "No testimonials page",
        "New patients have no stories from people like them.",
    ),
    "reviews_page": (
        "No reviews page",
        "Good reviews live only on Google, not where visitors decide to book.",
    ),
    "case_study_pages": (
        "No case studies",
        "There is no worked example showing a treatment from start to finish.",
    ),
    "video_testimonials": (
        "No video testimonials",
        "Video from real patients is the strongest proof a clinic can show.",
    ),
    "provider_credentials": (
        "Provider credentials are not shown",
        "Patients look for the medical director and their training before booking.",
    ),
    "no_posts": (
        "No blog posts found",
        "There is no fresh content answering the questions patients search for.",
    ),
    "blog_links": (
        "Blog posts do not link to treatment pages",
        "Readers and Google are not guided from articles to the pages that book.",
    ),
    "no_video": (
        "No patient video on the site",
        "Video keeps visitors on the page and builds trust faster than text.",
    ),
}


def grade_for(score: float) -> str:
    if score >= GRADE_A:
        return "A"
    if score >= GRADE_B:
        return "B"
    if score >= GRADE_C:
        return "C"
    if score >= GRADE_D:
        return "D"
    return "F"


def _points(status: object) -> float | None:
    return {"ok": 1.0, "warn": 0.5, "fail": 0.0}.get(str(status))


def _check_issue(item: dict[str, Any]) -> dict[str, str]:
    """Issue for a home-page check; tagged so it is counted by status, not as a miss."""
    key = str(item.get("key", ""))
    title, detail = ISSUE_COPY.get(key) or (
        f"{item.get('label') or key} needs attention",
        str(item.get("value") or "Not found on the site"),
    )
    return {"title": title, "detail": detail, "check": "yes"}


def _miss(key: str, title: str | None = None) -> dict[str, str]:
    copy_title, detail = MISS_COPY[key]
    return {"title": title or copy_title, "detail": detail}


# Each scorer returns (score 0-100 or None when there is no data, issues).
Scored = tuple[float | None, list[dict[str, str]]]


def _gbp(sections: dict[str, Any]) -> Scored:
    business = sections.get("business") or {}
    gbp = business.get("gbp")
    if not gbp or not gbp.get("matched"):
        return None, []
    nap = business.get("nap") or {}
    score, issues = float(GBP_MATCHED), []
    for earned, points, miss in (
        (gbp.get("verified") is True, GBP_VERIFIED, "gbp_unverified"),
        (bool(gbp.get("primary_category")), GBP_PRIMARY_CATEGORY, "gbp_category"),
        (gbp.get("website_links_to_gbp") is True, GBP_WEBSITE_LINKS, "gbp_link"),
        (nap.get("consistent_with_gbp") is True, GBP_PHONE_MATCHES, "gbp_phone"),
    ):
        if earned:
            score += points
        # an unknown phone match (no number to compare) costs points but is not called out
        elif not (miss == "gbp_phone" and nap.get("consistent_with_gbp") is None):
            issues.append(_miss(miss))
    return score, issues


def _reviews(sections: dict[str, Any]) -> Scored:
    gbp = (sections.get("business") or {}).get("gbp")
    if not gbp or not gbp.get("matched"):
        return None, []
    score, issues = 0.0, []
    rating, count = gbp.get("rating"), gbp.get("review_count")
    if isinstance(rating, int | float) and rating >= REVIEWS_RATING_TOP:
        score += REVIEWS_RATING_TOP_POINTS
    elif isinstance(rating, int | float) and rating >= REVIEWS_RATING_OK:
        score += REVIEWS_RATING_OK_POINTS
    if not isinstance(rating, int | float) or rating < REVIEWS_RATING_TOP:
        issues.append(
            {
                "title": f"Google rating is {rating}"
                if isinstance(rating, int | float)
                else "No Google rating yet",
                "detail": f"Clinics rated {REVIEWS_RATING_TOP} or higher win most of the clicks in the map results.",
            }
        )
    if isinstance(count, int | float) and count >= REVIEWS_COUNT_TOP:
        score += REVIEWS_COUNT_TOP_POINTS
    elif isinstance(count, int | float) and count >= REVIEWS_COUNT_OK:
        score += REVIEWS_COUNT_OK_POINTS
    if not isinstance(count, int | float) or count < REVIEWS_COUNT_TOP:
        issues.append(
            {
                "title": f"Only {int(count or 0)} Google reviews",
                "detail": "A thin review count makes patients pick a busier looking competitor.",
            }
        )
    if gbp.get("review_link_on_site") is True:
        score += REVIEWS_LINK
    else:
        issues.append(_miss("review_link"))
    return score, issues


def _service_pages(sections: dict[str, Any]) -> Scored:
    site = sections.get("site")
    if not site:
        return None, []
    clusters = (site.get("services") or {}).get("clusters") or []
    if not clusters:
        return 0.0, [_miss("no_services")]
    values: list[tuple[float, dict[str, str] | None]] = []
    unread: list[float] = []
    for c in clusters:
        found, expected = c.get("found") or 0, c.get("expected") or 0
        coverage = min(found / expected, 1.0) if expected else float(found > 0)
        present, missing = c.get("topics_present") or [], c.get("topics_missing") or []
        if present or missing:  # topics known (AI pass ran for this service)
            topics = min(len(present) / SERVICE_TOPICS, 1.0)
            value = (
                SERVICE_COVERAGE_SHARE * coverage
                + (1 - SERVICE_COVERAGE_SHARE) * topics
            )
        else:
            unread.append(coverage)
            continue
        issue = None
        if value < 1:
            gaps = []
            if coverage < 1:
                gaps.append(f"{found} of {expected} expected pages")
            if missing:
                gaps.append(
                    f"misses {len(missing)} of {SERVICE_TOPICS} patient questions"
                )
            issue = {
                "title": f"{c.get('service')} pages are thin",
                "detail": f"{'; '.join(gaps) or 'Coverage is incomplete'}. Searches for this treatment go to competitors.",
            }
        values.append((value, issue))
    if not values:
        return 100 * sum(unread) / len(unread), []
    worst_first = sorted(values, key=lambda v: v[0])
    issues = [i for _, i in worst_first if i]
    return 100 * sum(v for v, _ in values) / len(values), issues


def _service_area(sections: dict[str, Any]) -> Scored:
    site = sections.get("site")
    if not site:
        return None, []
    cities = site.get("cities") or {}
    found = cities.get("pages_found") or 0
    score = AREA_CITY_POINTS * min(found / AREA_CITY_PAGES_FULL, 1.0)
    issues = []
    if found == 0:
        issues.append(_miss("no_city_pages"))
    elif found < AREA_CITY_PAGES_FULL:
        issues.append(
            {
                "title": f"Only {found} city pages",
                "detail": "Patients in other nearby towns cannot find a page built for their search.",
            }
        )
    if cities.get("hub_page"):
        score += AREA_HUB_POINTS
    else:
        issues.append(_miss("no_hub"))
    unbuilt = cities.get("claimed_not_built") or []
    if unbuilt:
        score -= min(AREA_UNBUILT_PENALTY * len(unbuilt), AREA_UNBUILT_MAX_PENALTY)
        issues.insert(
            0,
            {
                "title": f"Serves {', '.join(unbuilt[:3])} but has no page for {'it' if len(unbuilt) == 1 else 'them'}",
                "detail": "The site says it serves these areas, yet nobody searching there will find it.",
            },
        )
    return max(score, 0.0), issues


def _getting_the_call(sections: dict[str, Any]) -> Scored:
    convert = sections.get("convert")
    if not convert:
        return None, []
    checks = {str(c.get("key")): c for c in convert.get("checks") or []}
    # (field, check key whose status wins when present, fallback value, miss copy key)
    items: tuple[tuple[str, str | None, bool, str | None], ...] = (
        ("online_booking", "online_booking", bool(convert.get("online_booking")), None),
        (
            "phone_in_header",
            None,
            bool(convert.get("phone_in_header")),
            "phone_in_header",
        ),
        ("click_to_call", "click_to_call", bool(convert.get("click_to_call")), None),
        ("forms", "contact_form", (convert.get("forms_count") or 0) > 0, None),
        ("chat_widget", None, bool(convert.get("chat_widget")), "chat_widget"),
        # never detected yet (always False): costs points but is not called out
        ("cta_above_fold", None, bool(convert.get("cta_above_fold")), None),
    )
    total, issues = 0.0, []
    for _, check_key, value, miss in items:
        check = checks.get(check_key or "")
        status = _points(check.get("status")) if check else None
        if status is not None and check is not None:
            total += status
            if status < 1:
                issues.append(_check_issue(check))
        else:
            total += float(value)
            if not value and miss:
                issues.append(_miss(miss))
    return 100 * total / len(items), issues


def _site_fundamentals(sections: dict[str, Any], speed_unavailable: bool) -> Scored:
    on_page = sections.get("on_page")
    if not on_page:
        return None, []
    parts: list[tuple[float, float]] = []  # (share, 0-1 value)
    issues: list[dict[str, str]] = []
    statuses = [
        (item, p)
        for item in on_page.get("essentials") or []
        if (p := _points(item.get("status"))) is not None
    ]
    if statuses:
        parts.append(
            (FUNDAMENTALS_ESSENTIALS, sum(p for _, p in statuses) / len(statuses))
        )
        issues += [_check_issue(item) for item, p in statuses if p < 1]
    schema = sections.get("schema")
    if schema:
        local = bool(schema.get("has_local_business"))
        clean = not schema.get("parse_errors")
        parts.append((FUNDAMENTALS_SCHEMA, 0.5 * local + 0.5 * clean))
        if not local:
            issues.append(_miss("no_local_business"))
        if not clean:
            issues.append(_miss("schema_errors"))
    if (sections.get("site") or {}).get("placeholder_pages"):
        issues.insert(0, _miss("placeholder_text"))
    performance = (on_page.get("pagespeed") or {}).get("mobile_performance")
    if not speed_unavailable and isinstance(performance, int | float):
        speed = (
            100
            if performance >= SPEED_GOOD
            else SPEED_OK_SCORE
            if performance >= SPEED_OK
            else 0
        )
        parts.append((FUNDAMENTALS_SPEED, speed / 100))
        if performance < SPEED_GOOD:
            issues.insert(
                0,
                {
                    "title": f"Slow on phones (mobile PageSpeed {round(performance)})",
                    "detail": "Slow pages lose mobile visitors before they ever see a phone number.",
                },
            )
    shares = sum(s for s, _ in parts)
    if not shares:
        return None, []
    return 100 * sum(s * v for s, v in parts) / shares, issues


def _content_and_proof(sections: dict[str, Any]) -> Scored:
    site = sections.get("site")
    if not site:
        return None, []
    proof = site.get("proof") or {}
    credentials = any(
        t.get("key") == "provider_credentials" and t.get("status") == "found"
        for t in site.get("trust") or []
    )
    items = (
        ("before_after_gallery", bool(proof.get("before_after_gallery"))),
        ("testimonial_pages", (proof.get("testimonial_pages") or 0) > 0),
        ("reviews_page", bool(proof.get("reviews_page"))),
        ("case_study_pages", (proof.get("case_study_pages") or 0) > 0),
        ("video_testimonials", bool(proof.get("video_testimonials"))),
        ("provider_credentials", credentials),
    )
    issues = [_miss(key) for key, ok in items if not ok]
    return 100 * sum(ok for _, ok in items) / len(items), issues


def _post_age_days(value: object, now: datetime) -> int | None:
    try:
        return (now.date() - date.fromisoformat(str(value)[:10])).days
    except ValueError:
        return None


def _supporting_content(sections: dict[str, Any], now: datetime) -> Scored:
    site = sections.get("site")
    if not site:
        return None, []
    blog = site.get("blog") or {}
    score, issues = 0.0, []
    age = _post_age_days(blog.get("last_post_at"), now)
    if age is not None and age <= BLOG_FRESH_DAYS:
        score += BLOG_FRESH_POINTS
    elif age is not None and age <= BLOG_RECENT_DAYS:
        score += BLOG_RECENT_POINTS
    year = blog.get("posts_last12_months") or 0
    score += BLOG_VOLUME_POINTS * min(year / BLOG_POSTS_YEAR_FULL, 1.0)
    # Counts come from dated posts only. When most posts have no date they are minimums, so
    # report no recency or volume issue: "only 1 post this year" would be a guess.
    posts, dated = blog.get("post_count") or 0, blog.get("dated_posts")
    dates_unknown = (
        posts > 0 and dated is not None and dated < posts * BLOG_DATES_MIN_SHARE
    )
    if age is None and not year and not posts:
        issues.append(_miss("no_posts"))
    elif dates_unknown:
        pass
    else:
        if age is None or age > BLOG_FRESH_DAYS:
            issues.append(
                {
                    "title": "No recent blog post"
                    if age is None
                    else f"Last blog post was {age // 30} months ago",
                    "detail": "Google and patients read a quiet blog as a quiet clinic.",
                }
            )
        if year < BLOG_POSTS_YEAR_FULL:
            issues.append(
                {
                    "title": f"Only {year} blog posts in the last 12 months",
                    "detail": "Regular posts answer the questions patients search before booking.",
                }
            )
    if blog.get("links_to_services") is True:
        score += BLOG_LINKS_POINTS
    elif (
        issues
        and issues[0]["title"] != MISS_COPY["no_posts"][0]
        or dates_unknown
        and blog.get("links_to_services") is False
    ):
        issues.append(_miss("blog_links"))
    return score, issues


def _social_and_video(sections: dict[str, Any]) -> Scored:
    business, site = sections.get("business"), sections.get("site")
    if not business and not site:
        return None, []
    count = len((business or {}).get("socials") or [])
    video = bool(((site or {}).get("proof") or {}).get("video_testimonials"))
    score = SOCIAL_POINTS * min(count / SOCIAL_PROFILES_FULL, 1.0)
    issues = []
    if count < SOCIAL_PROFILES_FULL:
        issues.append(
            {
                "title": f"Only {count} social profiles linked",
                "detail": "Patients check Instagram and Facebook before trusting a clinic.",
            }
        )
    if video:
        score += SOCIAL_VIDEO_POINTS
    else:
        issues.append(_miss("no_video"))
    return score, issues


def _status_counts(sections: dict[str, Any]) -> tuple[int, int]:
    """Home-page check statuses, as before: `fail` is an issue, `warn` a warning."""
    checks = [
        *((sections.get("on_page") or {}).get("essentials") or []),
        *((sections.get("convert") or {}).get("checks") or []),
    ]
    fails = sum(1 for c in checks if c.get("status") == "fail")
    warns = sum(1 for c in checks if c.get("status") == "warn")
    return fails, warns


def compute(
    sections: dict[str, Any],
    *,
    pagespeed_ok: bool | None = None,
    domain: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the `overview` section for a finished audit.

    `pagespeed_ok`: True when PageSpeed ran, False when it failed or timed out, None when it
    was not run (no key). Without a mobile score the speed part is dropped and the result
    is provisional.
    """
    now = now or datetime.now(UTC)
    speed = ((sections.get("on_page") or {}).get("pagespeed") or {}).get(
        "mobile_performance"
    )
    speed_unavailable = pagespeed_ok is False or not isinstance(speed, int | float)
    scorers: dict[str, Callable[[], Scored]] = {
        "google_business_profile": lambda: _gbp(sections),
        "reviews": lambda: _reviews(sections),
        "service_pages": lambda: _service_pages(sections),
        "service_area": lambda: _service_area(sections),
        "getting_the_call": lambda: _getting_the_call(sections),
        "site_fundamentals": lambda: _site_fundamentals(sections, speed_unavailable),
        "content_and_proof": lambda: _content_and_proof(sections),
        "supporting_content": lambda: _supporting_content(sections, now),
        "social_and_video": lambda: _social_and_video(sections),
    }
    results = {key: scorers[key]() for key, _, _ in CATEGORIES}
    scores = {
        key: max(0, min(100, round(s)))
        for key, (s, _) in results.items()
        if s is not None
    }
    reasons: list[str] = []
    if "google_business_profile" not in scores:
        reasons.append(NO_GBP)
    if speed_unavailable:
        reasons.append(NO_PAGESPEED)
    for key, label, _ in CATEGORIES[2:]:  # GBP and reviews are covered by NO_GBP
        if key not in scores:
            reasons.append(f"{label} not assessed")

    included = sum(_WEIGHT[k] for k in scores)
    overall = (
        round(sum(_WEIGHT[k] * s for k, s in scores.items()) / included)
        if included
        else None
    )
    categories = [
        {
            "key": key,
            "label": label,
            "weight": weight,
            "score": scores.get(key),
            "grade": grade_for(scores[key]) if key in scores else None,
            # share of the 100-point total this category cost, after rescaling
            "points_lost": round(weight * 100 / included * (100 - scores[key]) / 100, 1)
            if key in scores
            else None,
            "excluded": key not in scores,
        }
        for key, label, weight in CATEGORIES
    ]

    # Rank by what each category costs (weight x points missed); keep order within one.
    ranked = sorted(scores, key=lambda k: _WEIGHT[k] * (100 - scores[k]), reverse=True)
    top_issues = [
        {"category": key, "title": issue["title"], "detail": issue["detail"]}
        for key in ranked
        for issue in results[key][1][:ISSUES_PER_CATEGORY]
    ][:MAX_TOP_ISSUES]

    # issue_count: failed checks plus every miss found by the category rules;
    # warning_count: home-page checks that only warn (warn checks are not misses).
    fails, warns = _status_counts(sections)
    misses = sum(
        1 for key in scores for issue in results[key][1] if "check" not in issue
    )
    grade = grade_for(overall) if overall is not None else None
    head = f"{domain}: " if domain else ""
    summary = (
        f"{head}{overall}/100 ({grade}). "
        + (
            "Top issues: " + "; ".join(i["title"] for i in top_issues[:3]) + "."
            if top_issues
            else "No major issues found."
        )
        + (f" Provisional: {', '.join(reasons)}." if reasons else "")
        if overall is not None
        else f"{head}not enough data to score."
    )
    return {
        "score": overall,
        "grade": grade,
        "provisional": bool(reasons),
        "provisional_reasons": reasons,
        "categories": categories,
        "top_issues": top_issues,
        "issue_count": fails + misses,
        "warning_count": warns,
        "summary_text": summary,
    }
