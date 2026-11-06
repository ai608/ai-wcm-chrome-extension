from app.services import area_pages

HOME = "https://x.com"


def words(prefix: str, city: str = "", n: int = 320) -> str:
    """n distinct words; with a city, its name sits in every tenth place (a city-swap template)."""
    return " ".join(
        f"{prefix}{i} {city}" if city and i % 10 == 0 else f"{prefix}{i}"
        for i in range(n)
    )


BODY = words("body")


def page(title: str, h1: str, text: str = BODY, head: str = "") -> str:
    return (
        f"<html><head><title>{title}</title>{head}</head>"
        f"<body><h1>{h1}</h1><p>{text}</p></body></html>"
    )


def graded(areas, pages, urls=None):
    out = area_pages.grade(areas, urls or list(pages), pages)
    return {g["name"]: g for g in out}


def test_status_covered_mentioned_missing():
    pages = {
        f"{HOME}/": page("Glow", "Glow", BODY + " We serve Round Rock too."),
        f"{HOME}/tampa/": page("Tampa weight loss", "Weight loss in Tampa"),
    }
    g = graded(["Tampa", "Round Rock", "Ocala"], pages)
    assert g["Tampa"]["status"] == "covered" and g["Tampa"]["issues"] == []
    assert (
        g["Round Rock"]["status"] == "mentioned"
    )  # named in the text, no page of its own
    assert g["Ocala"]["status"] == "missing"


def test_a_page_of_its_own_by_title_and_h1_without_the_name_in_the_address():
    pages = {f"{HOME}/spa/": page("Med spa in Tampa", "Tampa med spa")}
    assert graded(["Tampa"], pages)["Tampa"]["pages"] == [f"{HOME}/spa/"]


def test_blog_post_with_the_city_is_no_page_of_its_own():
    pages = {
        f"{HOME}/blog/best-tampa-spas/": page("Best Tampa spas", "Best Tampa spas")
    }
    assert graded(["Tampa"], pages)["Tampa"]["status"] == "mentioned"


def test_thin_noindex_and_missing_title_h1():
    pages = {
        f"{HOME}/tampa/": page("Welcome", "Hello", "Short page."),
        f"{HOME}/sarasota/": page(
            "Sarasota",
            "Sarasota",
            head='<meta name="robots" content="noindex, follow">',
        ),
    }
    g = graded(["Tampa", "Sarasota"], pages)
    assert g["Tampa"]["status"] == "needs_work"
    assert g["Tampa"]["issues"] == ["thin", "title_h1"]
    assert g["Sarasota"]["issues"] == ["noindex"]


def test_pages_that_only_swap_the_city_name_are_copies():
    pages = {
        f"{HOME}/tampa/": page("Tampa", "Tampa", words("t", "Tampa")),
        f"{HOME}/sarasota/": page("Sarasota", "Sarasota", words("t", "Sarasota")),
        f"{HOME}/ocala/": page("Ocala", "Ocala", words("other")),
    }
    g = graded(["Tampa", "Sarasota", "Ocala"], pages)
    assert (
        g["Tampa"]["issues"] == ["duplicate"]
        and g["Tampa"]["duplicate_of"] == "Sarasota"
    )
    assert g["Sarasota"]["duplicate_of"] == "Tampa"
    assert g["Ocala"]["issues"] == [] and g["Ocala"]["status"] == "covered"


def test_a_page_not_crawled_is_covered_with_nothing_to_check():
    g = graded(["Tampa"], {}, [f"{HOME}/tampa/"])
    assert g["Tampa"]["status"] == "covered" and g["Tampa"]["issues"] == []


def test_the_page_that_names_the_area_is_the_one_judged():
    """/florida/ names the state in its title; the longer city page under it does not, and
    must not make "Florida" look like a page with no area in its title."""
    pages = {
        f"{HOME}/florida/": page(
            "Florida weight loss", "Care across Florida", words("f")
        ),
        f"{HOME}/loss/florida/tampa/": page("Tampa", "Tampa", words("t", n=900)),
    }
    g = graded(["Florida"], pages)["Florida"]
    assert g["status"] == "covered" and g["issues"] == []
