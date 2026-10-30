"""Lookup tables for the website audit: who the clinic's vendors are and which services we know.

Data only, no logic and no imports. Add a vendor or a service here and every part of the audit
sees it: before this file, site_audit and site_crawl each kept their own booking list and the
two had drifted apart (7 vendors against 12).

Matching rules, so a new entry works the first time:
- BOOKING and CHAT keys are matched against the LOWER-CASED page source: write them lower case.
- TRUST words are matched against the lower-cased URL path, TRUST_LINK_TEXT against the
  lower-cased text of a menu link.
- SERVICES terms are matched against lower-cased URLs and text, with "-" read as a space.
- PLATFORMS markers are matched against the RAW source (case matters), first match wins.
- Tunable numbers (timeouts, caps) and scoring weights stay next to the code they tune.
"""

# Service name -> words that mean the clinic offers it. Order is the order of the report.
SERVICES = {
    "Neurotoxins": ("botox", "dysport", "xeomin", "neurotoxin"),
    "Dermal Fillers": ("filler", "juvederm", "restylane"),
    "Medical Weight Loss": ("weight loss", "semaglutide", "tirzepatide", "glp-1"),
    "IV Therapy": ("iv therapy", "iv hydration", "nad+", "vitamin injection"),
    "Hormone Replacement": ("hormone", "hrt", "trt", "testosterone"),
    "Laser Hair Removal": ("laser hair removal",),
    "Microneedling": ("microneedling", "micro needling"),
    "Chemical Peels & Facials": ("chemical peel", "hydrafacial", "facial", "facials"),
    "Body Contouring": ("body contour", "coolsculpting", "emsculpt"),
    "PRP / Hair Restoration": ("prp", "hair restoration"),
    "Chiropractic": ("chiropractic", "chiropractor"),
    "Functional Medicine": ("functional medicine",),
}

SOCIAL_HOSTS = (
    ("facebook", "facebook.com"),
    ("instagram", "instagram.com"),
    ("tiktok", "tiktok.com"),
    ("youtube", "youtube.com"),
    ("linkedin", "linkedin.com"),
    ("x", "x.com"),
)

# Site builder -> marker in the page source. Frameworks come first: a Gatsby or Next.js site
# can still load images from wp-content/.
PLATFORMS = (
    ("Gatsby", "data-gatsby-head"),
    ("Next.js", "__NEXT_DATA__"),
    ("Webflow", "data-wf-site"),
    ("Wix", "wixstatic.com"),
    ("Squarespace", "squarespace.com"),
    ("Shopify", "cdn.shopify.com"),
    ("Kajabi", "Kajabi."),
    ("WordPress", "wp-content/"),
)

# Trust page: (key, label, words in its URL). Used for the home page and for every mapped URL.
TRUST = (
    ("about_page", "About page", ("/about",)),
    (
        "team_page",
        "Providers / team page",
        ("/team", "/providers", "/our-staff", "/meet-"),
    ),
    ("faq_page", "FAQ page", ("/faq",)),
    ("pricing_page", "Pricing page", ("/pricing", "/prices", "/price-list")),
    ("financing_page", "Financing page", ("/financing", "/payment-plans")),
    ("privacy_policy", "Privacy policy", ("/privacy",)),
)

# Trust page key -> words in a menu link's text ("Cost" is the pricing page, "About Mary Ann"
# the about page). Used when the URL does not say it. Matched against lower-cased text.
TRUST_LINK_TEXT = {
    "about_page": ("about",),
    "team_page": ("team", "provider", "staff", "meet"),
    "faq_page": ("faq", "questions"),
    "pricing_page": ("cost", "pricing", "price", "fees", "rates"),
    "financing_page": ("financ", "payment"),
    "privacy_policy": ("privacy",),
}

# Online booking tool: marker (lower case) -> name.
BOOKING = {
    "joinblvd.com": "Boulevard",
    "vagaro.com": "Vagaro",
    "mindbodyonline.com": "Mindbody",
    "zenoti.com": "Zenoti",
    "janeapp.com": "Jane",
    "acuityscheduling.com": "Acuity",
    "calendly.com": "Calendly",
    "squareup.com": "Square",
    "leadconnectorhq.com": "GoHighLevel",
    "msgsndr.com": "GoHighLevel",
    "setmore.com": "Setmore",
    "glossgenius.com": "GlossGenius",
}

# Chat widget: marker (lower case) -> name.
CHAT = {
    "podium.com": "Podium",
    "birdeye.com": "Birdeye",
    "intercom": "Intercom",
    "tidio": "Tidio",
    "widgets.leadconnectorhq.com": "GHL chat",
    "livechatinc": "LiveChat",
}
