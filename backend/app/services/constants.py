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
    ("SeoToaster", "seotoaster.com"),
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

LOCAL_BUSINESS_TYPES = frozenset(
    {
        "localbusiness",
        "medicalbusiness",
        "medicalclinic",
        "dayspa",
        "healthandbeautybusiness",
        "beautysalon",
        "healthclub",
        "physician",
        "dentist",
    }
)

PLACEHOLDER_TEXT = ("lorem ipsum", "sample title", "heading text here")

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

# Structured data type -> (required, recommended) properties, from Google's LocalBusiness and
# Organization guides. Keys are lower case; local business types share one row.
SCHEMA_PROPS = {
    "local": (
        ("name", "address"),
        ("telephone", "url", "geo", "openingHoursSpecification", "priceRange", "image"),
    ),
    "organization": ((), ("name", "url", "logo", "sameAs")),
    "person": (("name",), ("url", "image", "jobTitle")),
    "physician": (("name",), ("url", "image", "medicalSpecialty")),
    "website": ((), ("name", "url")),
    "breadcrumblist": (("itemListElement",), ()),
}

GENERIC_TITLES = frozenset(
    {"home", "homepage", "untitled", "welcome", "index", "just another wordpress site"}
)

REFERENCE_HOSTS = (
    ".gov",
    ".edu",
    "who.int",
    "pubmed",
    "mayoclinic.org",
    "clevelandclinic.org",
    "webmd.com",
    "healthline.com",
)
