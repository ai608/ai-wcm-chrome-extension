import type {
  AiVisibility,
  Audit,
  CategoryKey,
  CheckStatus,
  DomainOverview,
  Grade,
  LocalCompetitors,
  SiteSection,
} from '@/lib/api/research-types'

export const STRONG_DOMAIN = 'glowaesthetics.com'

const CLUSTERS: Record<string, string[]> = {
  'Neurotoxins (Botox / Dysport / Xeomin)': [
    'Botox cost',
    'Botox for forehead lines',
    'Dysport vs Botox',
    'Xeomin',
    'Botox for masseter',
    'Preventative Botox',
    'Botox aftercare',
    'Botox FAQ',
  ],
  'Dermal Fillers': [
    'Lip filler',
    'Cheek filler',
    'Under-eye filler',
    'Jawline filler',
    'Filler cost',
    'Filler vs Botox',
    'Filler aftercare',
    'Juvederm vs Restylane',
  ],
  'Medical Weight Loss (GLP-1)': [
    'Semaglutide',
    'Tirzepatide',
    'GLP-1 cost',
    'Weight loss program',
    'Compounded vs brand',
    'Weight loss FAQ',
    'Medical weight loss consult',
    'Side effects',
    'Weight loss for women over 40',
  ],
  'IV Therapy': [
    'Hangover IV',
    'NAD+ IV',
    "Myers' cocktail",
    'Immunity IV',
    'Hydration IV',
    'Vitamin injections',
    'B12 shots',
    'Athletic recovery IV',
    'Mobile IV',
    'IV therapy cost',
    'IV therapy FAQ',
  ],
  'Hormone Replacement (HRT / TRT)': [
    'HRT for women',
    'TRT for men',
    'Bioidentical hormones',
    'Menopause treatment',
    'Hormone testing',
    'Pellet therapy',
    'HRT cost',
    'HRT FAQ',
  ],
  'Laser Hair Removal': [
    'Laser hair removal cost',
    'Bikini laser',
    'Underarm laser',
    'Full body laser',
    'Laser hair removal FAQ',
    'Men’s laser hair removal',
    'Preparation',
    'Packages',
  ],
  'Microneedling / RF': [
    'Microneedling',
    'RF microneedling',
    'Microneedling for acne scars',
    'Microneedling cost',
    'Microneedling aftercare',
    'PRP microneedling',
  ],
  'Chemical Peels & Facials': [
    'Chemical peel',
    'HydraFacial',
    'Medical-grade facial',
    'Peel for hyperpigmentation',
    'Peel cost',
    'Facial memberships',
  ],
  'Body Contouring': [
    'CoolSculpting',
    'EmSculpt',
    'Skin tightening',
    'Body contouring cost',
    'Cellulite treatment',
    'Body contouring FAQ',
  ],
  'PRP / Hair Restoration': [
    'PRP for hair loss',
    'Hair restoration cost',
    'PRP for face',
    'Hair loss consult',
    'PRP aftercare',
    'Exosome therapy',
  ],
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

function services(domain: string, strong: boolean): SiteSection['services'] {
  const names = Object.keys(CLUSTERS)
  const clusters = names.map((service, i) => {
    const topics = CLUSTERS[service] ?? []
    const keep = strong ? (i < 6 ? topics.length - (i % 3) : 0) : i === 0 ? 2 : i === 3 ? 1 : 0
    const present = topics.slice(0, keep)
    return {
      service,
      found: present.length,
      expected: topics.length,
      pages: present.map(
        (t) => `https://${domain}/${slug(service.split(' ')[0] ?? '')}/${slug(t)}/`,
      ),
      topicsPresent: present,
      topicsMissing: topics.slice(keep),
    }
  })
  return {
    clusterPagesFound: clusters.reduce((a, c) => a + c.found, 0),
    clusterPagesExpected: clusters.reduce((a, c) => a + c.expected, 0),
    clusters,
  }
}

function grade(score: number): Grade {
  return score >= 90 ? 'A' : score >= 80 ? 'B' : score >= 70 ? 'C' : score >= 60 ? 'D' : 'F'
}

const CAT_LABELS: Record<CategoryKey, string> = {
  gbp: 'Google Business Profile',
  reviews: 'Reviews',
  service_pages: 'Service pages',
  service_area: 'Service area',
  getting_the_call: 'Getting the call',
  site_fundamentals: 'Site fundamentals',
  content_proof: 'Content & proof',
  supporting_content: 'Supporting content',
  social_video: 'Social & video',
}

export function buildAudit(id: string, domain: string, url: string, startedAt: Date): Audit {
  const strong = domain === STRONG_DOMAIN
  const svc = services(domain, strong)
  const cat = (key: CategoryKey, s: number) => ({
    key,
    label: CAT_LABELS[key],
    score: s,
    grade: grade(s),
  })
  const categories = strong
    ? [
        cat('gbp', 92),
        cat('reviews', 88),
        cat('service_pages', 74),
        cat('service_area', 70),
        cat('getting_the_call', 85),
        cat('site_fundamentals', 82),
        cat('content_proof', 72),
        cat('supporting_content', 68),
        cat('social_video', 76),
      ]
    : [
        cat('service_pages', 28),
        cat('service_area', 0),
        cat('getting_the_call', 35),
        cat('site_fundamentals', 52),
        cat('content_proof', 30),
        cat('supporting_content', 24),
        cat('social_video', 40),
      ]
  const score = strong ? 78 : 32
  const topIssues = strong
    ? [
        {
          category: 'service_area' as const,
          title: 'Only 4 city pages for a multi-city service area',
          detail: 'Patients in nearby towns can’t find a page built for their search.',
        },
        {
          category: 'service_pages' as const,
          title: 'Hormone therapy has no FAQ or cost page',
          detail: 'High-intent searches like “HRT cost” land on competitors.',
        },
      ]
    : [
        {
          category: 'service_pages' as const,
          title: 'Only 3 of 70 expected treatment pages exist',
          detail:
            'Botox, fillers, IV therapy and weight loss are each covered by a single thin page, so most treatment searches never reach this clinic.',
        },
        {
          category: 'service_area' as const,
          title: 'No city or service-area pages',
          detail:
            'No map-radius coverage beyond the home market, usually the biggest local SEO gap.',
        },
        {
          category: 'getting_the_call' as const,
          title: 'No online booking detected',
          detail: 'Patients who find the site at night have no way to book without calling.',
        },
        {
          category: 'site_fundamentals' as const,
          title: 'No LocalBusiness schema',
          detail: 'Google gets no structured signal for the clinic name, address and hours.',
        },
        {
          category: 'content_proof' as const,
          title: 'No before/after gallery or provider bios',
          detail: 'Elective-treatment buyers look for proof and a medical director before booking.',
        },
        {
          category: 'supporting_content' as const,
          title: '160 blog posts but only 1 in the last 6 months',
          detail: 'Publishing stalled and posts do not link to treatment pages.',
        },
      ]
  const t = (key: string, label: string, ok: boolean, url?: string) => ({
    key,
    label,
    status: (ok ? 'found' : 'missing') as 'found' | 'missing',
    url: ok && url ? `https://${domain}${url}` : null,
  })
  const ok = (b: boolean, warn = false): CheckStatus => (b ? 'ok' : warn ? 'warn' : 'fail')
  const cities = strong ? ['Austin', 'Round Rock', 'Cedar Park', 'Pflugerville'] : []
  return {
    id,
    url,
    domain,
    status: 'ready',
    error: null,
    createdAt: startedAt.toISOString(),
    finishedAt: new Date(startedAt.getTime() + 6000).toISOString(),
    sectionState: {
      overview: 'ready',
      business: 'ready',
      on_page: 'ready',
      schema: 'ready',
      site: 'ready',
      convert: 'ready',
      research: 'ready',
    },
    overview: {
      score,
      grade: grade(score),
      provisional: !strong,
      categories,
      topIssues,
      issueCount: strong ? 3 : 14,
      warningCount: strong ? 6 : 9,
      summaryText: `${domain}: ${score}/100 (${grade(score)}). ${topIssues
        .map((i) => i.title)
        .join('; ')}.`,
    },
    business: {
      gbp: strong
        ? {
            matched: true,
            matchReason: 'phone + domain match',
            name: 'Glow Aesthetics Med Spa',
            verified: true,
            primaryCategory: 'Medical spa',
            categories: ['Medical spa', 'Skin care clinic', 'Weight loss service'],
            rating: 4.7,
            reviewCount: 212,
            address: '1200 S Congress Ave, Austin, TX 78704',
            phone: '(512) 555-0134',
            mapsUrl: 'https://maps.google.com/?cid=1234567890',
            lat: 30.2531,
            lng: -97.7494,
            websiteLinksToGbp: true,
            reviewLinkOnSite: true,
          }
        : {
            matched: false,
            matchReason: 'No candidate shared the phone number or domain',
            name: null,
            verified: null,
            primaryCategory: null,
            categories: [],
            rating: null,
            reviewCount: null,
            address: null,
            phone: null,
            mapsUrl: null,
            lat: null,
            lng: null,
            websiteLinksToGbp: false,
            reviewLinkOnSite: false,
          },
      company: {
        name: strong ? 'Glow Aesthetics Med Spa' : domain,
        industry: 'Health, Wellness & Fitness',
        employeeCount: strong ? 18 : 6,
        linkedinUrl: `https://www.linkedin.com/company/${slug(domain)}`,
        foundedYear: strong ? 2017 : 2011,
        technologies: [
          'WordPress',
          'Elementor',
          'Google Analytics',
          'Mailchimp',
          'Stripe',
          'Cloudflare',
          'Hotjar',
        ],
      },
      socials: [
        { network: 'instagram', url: `https://instagram.com/${slug(domain)}` },
        { network: 'facebook', url: `https://facebook.com/${slug(domain)}` },
        ...(strong
          ? [{ network: 'tiktok' as const, url: `https://tiktok.com/@${slug(domain)}` }]
          : []),
      ],
      nap: {
        name: strong ? 'Glow Aesthetics Med Spa' : null,
        address: strong ? '1200 S Congress Ave, Austin, TX' : null,
        phone: '(512) 555-0134',
        consistentWithGbp: strong ? true : null,
      },
    },
    onPage: {
      essentials: [
        {
          key: 'title',
          label: 'Title',
          value: strong ? 'Med Spa in Austin, TX | Glow Aesthetics' : 'Home',
          status: ok(strong, true),
          note: strong ? '41 chars' : '4 chars, too short',
        },
        {
          key: 'meta_description',
          label: 'Meta description',
          value: strong
            ? 'Botox, fillers, IV therapy and medical weight loss in Austin.'
            : '(missing)',
          status: ok(strong),
          note: strong ? '112 chars' : undefined,
        },
        { key: 'canonical', label: 'Canonical', value: url, status: 'ok' },
        { key: 'robots', label: 'Robots', value: 'index, follow', status: 'ok' },
        {
          key: 'h1',
          label: 'H1',
          value: strong ? 'Austin’s Medical Spa' : '(none)',
          status: ok(strong),
        },
        { key: 'https', label: 'HTTPS', value: 'Yes', status: 'ok' },
        { key: 'language', label: 'Language', value: 'en-US', status: 'ok' },
        {
          key: 'word_count',
          label: 'Word count',
          value: strong ? '1,240' : '186',
          status: ok(strong, true),
        },
        {
          key: 'image_alts',
          label: 'Image alts',
          value: strong ? '2 of 31 missing' : '3 of 7 missing',
          status: 'warn',
        },
        { key: 'viewport', label: 'Viewport', value: 'width=device-width', status: 'ok' },
        { key: 'platform', label: 'Platform', value: 'WordPress (Elementor)', status: 'info' },
        { key: 'favicon', label: 'Favicon', value: 'Present', status: 'ok' },
        {
          key: 'open_graph',
          label: 'Open Graph',
          value: strong ? 'Complete' : 'Missing og:image',
          status: ok(strong, true),
        },
      ],
      headings: {
        h1Count: strong ? 1 : 0,
        outline: [
          ...(strong ? [{ level: 1 as const, text: 'Austin’s Medical Spa' }] : []),
          { level: 2, text: 'Our treatments' },
          { level: 3, text: 'Botox & neurotoxins' },
          { level: 3, text: 'IV therapy' },
          { level: 2, text: 'Meet your providers' },
          { level: 2, text: 'Visit us' },
        ],
      },
      links: {
        internal: 34,
        external: 6,
        nofollow: 2,
        items: [
          {
            href: `https://${domain}/services/`,
            text: 'Services',
            kind: 'internal',
            nofollow: false,
          },
          {
            href: `https://${domain}/contact/`,
            text: 'Contact',
            kind: 'internal',
            nofollow: false,
          },
          { href: `https://${domain}/blog/`, text: '', kind: 'internal', nofollow: false },
          {
            href: 'https://instagram.com/glow',
            text: 'Instagram',
            kind: 'external',
            nofollow: true,
          },
          {
            href: 'https://maps.google.com/',
            text: 'Directions',
            kind: 'external',
            nofollow: false,
          },
        ],
      },
      images: {
        total: strong ? 31 : 7,
        missingAlt: strong ? 2 : 3,
        lazy: strong ? 24 : 0,
        items: [
          {
            src: `https://${domain}/wp-content/uploads/hero.jpg`,
            alt: strong ? 'Treatment room' : null,
            width: 1920,
            height: 1080,
          },
          {
            src: `https://${domain}/wp-content/uploads/team.jpg`,
            alt: 'Our team',
            width: 1200,
            height: 800,
          },
          {
            src: `https://${domain}/wp-content/uploads/botox.png`,
            alt: null,
            width: 800,
            height: 600,
          },
        ],
      },
      pagespeed: {
        mobilePerformance: strong ? 71 : 38,
        seo: strong ? 96 : 82,
        accessibility: strong ? 88 : 74,
        bestPractices: strong ? 92 : 79,
        lcpMs: strong ? 2600 : 5400,
        cls: strong ? 0.04 : 0.28,
      },
    },
    schema: {
      jsonLdCount: strong ? 3 : 1,
      parseErrors: 0,
      hasLocalBusiness: strong,
      hasFaqPage: strong,
      hasReviewMarkup: false,
      blocks: strong
        ? [
            {
              type: 'MedicalBusiness',
              presentProps: ['name', 'address', 'telephone', 'openingHours', 'geo'],
              missingRecommended: ['aggregateRating', 'priceRange'],
            },
            { type: 'FAQPage', presentProps: ['mainEntity'], missingRecommended: [] },
            {
              type: 'WebSite',
              presentProps: ['name', 'url'],
              missingRecommended: ['potentialAction'],
            },
          ]
        : [
            {
              type: 'WebSite',
              presentProps: ['name', 'url'],
              missingRecommended: ['potentialAction'],
            },
          ],
      raw: JSON.stringify(
        strong
          ? {
              '@context': 'https://schema.org',
              '@type': 'MedicalBusiness',
              name: 'Glow Aesthetics Med Spa',
              telephone: '(512) 555-0134',
            }
          : { '@context': 'https://schema.org', '@type': 'WebSite', name: domain, url },
        null,
        2,
      ),
    },
    site: {
      platform: { name: 'WordPress', detail: 'Elementor' },
      pagesCrawled: strong ? 84 : 41,
      services: svc,
      cities: {
        pagesFound: cities.length,
        hubPage: strong,
        cityPages: cities,
        claimedNotBuilt: strong ? ['Georgetown', 'Leander'] : ['Denver', 'Aurora', 'Lakewood'],
      },
      proof: {
        beforeAfterGallery: strong,
        testimonialPages: strong ? 2 : 0,
        reviewsPage: strong,
        caseStudyPages: strong ? 3 : 0,
        videoTestimonials: false,
      },
      blog: {
        url: `https://${domain}/blog/`,
        postCount: strong ? 46 : 160,
        lastPostAt: strong ? '2026-10-02T00:00:00Z' : '2026-04-18T00:00:00Z',
        postsLast6Months: strong ? 9 : 1,
        postsLast12Months: strong ? 17 : 3,
        linksToServices: strong,
        posts: [
          {
            url: `https://${domain}/blog/botox-vs-dysport/`,
            title: 'Botox vs Dysport: which is right for you?',
            publishedAt: '2026-10-02T00:00:00Z',
          },
          {
            url: `https://${domain}/blog/glp-1-faq/`,
            title: 'GLP-1 weight loss: what to expect',
            publishedAt: '2026-09-11T00:00:00Z',
          },
          {
            url: `https://${domain}/blog/summer-skin/`,
            title: 'Summer skin care tips',
            publishedAt: null,
          },
        ],
      },
      trust: [
        t('provider_bios', 'Provider bios', strong, '/team/'),
        t('medical_director', 'Medical director named', strong, '/team/'),
        t('credentials_licenses', 'Credentials & licenses', strong, '/about/'),
        t('about_page', 'About page', true, '/about/'),
        t('faq_page', 'FAQ page', strong, '/faq/'),
        t('pricing_page', 'Pricing page', false),
        t('membership_plans', 'Membership plans', strong, '/membership/'),
        t('financing', 'Financing', strong, '/financing/'),
        t('reviews_page', 'Reviews page', strong, '/reviews/'),
        t('before_after', 'Before & after gallery', strong, '/results/'),
        t('awards_press', 'Awards & press', false),
        t('privacy_policy', 'Privacy policy', true, '/privacy/'),
        t('accessibility_statement', 'Accessibility statement', false),
      ],
    },
    convert: {
      bookingPlatform: strong ? 'Boulevard' : null,
      onlineBooking: strong,
      phoneInHeader: true,
      clickToCall: strong,
      formsCount: strong ? 3 : 1,
      chatWidget: strong ? 'Podium' : null,
      ctaAboveFold: strong,
      offersOrSpecials: strong,
      financingMentioned: strong,
      textUs: strong,
      checks: [
        {
          key: 'booking',
          label: 'Online booking',
          status: ok(strong),
          note: strong ? 'Boulevard' : 'No online booking detected',
        },
        { key: 'phone_header', label: 'Phone number in header', status: 'ok' },
        { key: 'click_to_call', label: 'Click-to-call link', status: ok(strong) },
        { key: 'cta', label: 'CTA above the fold', status: ok(strong, true) },
        {
          key: 'chat',
          label: 'Chat widget',
          status: ok(strong, true),
          note: strong ? 'Podium' : undefined,
        },
        { key: 'offers', label: 'Offers or specials', status: ok(strong, true) },
        { key: 'financing', label: 'Financing mentioned', status: ok(strong, true) },
        { key: 'text_us', label: 'Text us', status: ok(strong, true) },
      ],
    },
    research: {
      domainOverview: { state: 'not_run', data: null, error: null, ranAt: null },
      localCompetitors: { state: 'not_run', data: null, error: null, ranAt: null },
      aiVisibility: { state: 'not_run', data: null, error: null, ranAt: null },
    },
  }
}

export function domainOverviewFixture(strong: boolean): DomainOverview {
  return {
    domainRating: strong ? 38 : 9,
    organicTraffic: strong ? 2400 : 120,
    organicKeywords: strong ? 640 : 48,
    referringDomains: strong ? 96 : 14,
    backlinks: strong ? 1800 : 61,
    topKeywords: [
      { keyword: 'med spa austin', position: strong ? 6 : 31, volume: 1900, url: null },
      { keyword: 'botox austin', position: strong ? 9 : 44, volume: 1300, url: null },
      { keyword: 'iv therapy near me', position: strong ? 14 : 58, volume: 8100, url: null },
      { keyword: 'semaglutide austin', position: strong ? 11 : 72, volume: 880, url: null },
    ],
  }
}

export function competitorsFixture(query?: string, location?: string): LocalCompetitors {
  return {
    query: query || 'med spa',
    location: location || 'Austin, TX',
    items: [
      {
        rank: 1,
        name: 'Revive Medical Spa',
        rating: 4.9,
        reviewCount: 640,
        website: 'https://revivespa.example',
        isThisBusiness: false,
      },
      {
        rank: 2,
        name: 'Skin Lab Austin',
        rating: 4.8,
        reviewCount: 390,
        website: 'https://skinlab.example',
        isThisBusiness: false,
      },
      {
        rank: 3,
        name: 'Glow Aesthetics Med Spa',
        rating: 4.7,
        reviewCount: 212,
        website: 'https://glowaesthetics.com',
        isThisBusiness: true,
      },
      {
        rank: 4,
        name: 'The IV Bar',
        rating: 4.6,
        reviewCount: 158,
        website: null,
        isThisBusiness: false,
      },
    ],
  }
}

export function aiVisibilityFixture(strong: boolean, prompts: string[]): AiVisibility {
  const engines = ['ChatGPT', 'Gemini', 'Perplexity', 'Claude']
  return {
    prompts,
    engines: engines.map((engine, i) => {
      const cited = strong && i < 2
      return {
        engine,
        cited,
        citedBusinesses: cited
          ? ['Glow Aesthetics Med Spa', 'Revive Medical Spa']
          : ['Revive Medical Spa', 'Skin Lab Austin', 'The IV Bar'],
        answerExcerpt: cited
          ? 'For med spas in Austin, Glow Aesthetics Med Spa and Revive Medical Spa are frequently recommended for Botox and IV therapy…'
          : 'Top-rated options include Revive Medical Spa, Skin Lab Austin and The IV Bar, known for neurotoxins and medical weight loss…',
      }
    }),
  }
}
