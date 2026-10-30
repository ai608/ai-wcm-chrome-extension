import type {
  AiVisibility,
  Audit,
  CategoryKey,
  CheckStatus,
  DomainOverview,
  Grade,
  LocalCompetitors,
  OverviewSection,
  SiteSection,
  TraceEvent,
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
  return score >= 90 ? 'A' : score >= 75 ? 'B' : score >= 60 ? 'C' : score >= 45 ? 'D' : 'F'
}

// Same order, labels and weights as backend site_score.CATEGORIES.
const CATS: [CategoryKey, string, number][] = [
  ['google_business_profile', 'Google Business Profile', 15],
  ['reviews', 'Reviews', 10],
  ['service_pages', 'Service pages', 15],
  ['service_area', 'Service area', 10],
  ['getting_the_call', 'Getting the call', 15],
  ['site_fundamentals', 'Site fundamentals', 10],
  ['content_and_proof', 'Content and proof', 10],
  ['supporting_content', 'Supporting content', 10],
  ['social_and_video', 'Social and video', 5],
]

/** Placeholder the backend stores until the whole audit has finished. */
export const PENDING_OVERVIEW: OverviewSection = {
  score: null,
  grade: null,
  provisional: true,
  provisionalReasons: [],
  categories: [],
  topIssues: [],
  issueCount: 0,
  warningCount: 0,
  summaryText: '',
}

/** The final weighted score, worked out like backend site_score.compute. */
export function mockOverview(domain: string): OverviewSection {
  const strong = domain === STRONG_DOMAIN
  // Weak fixture: no Google profile, so GBP and reviews are excluded (provisional).
  const scores: Partial<Record<CategoryKey, number>> = strong
    ? {
        google_business_profile: 92,
        reviews: 88,
        service_pages: 74,
        service_area: 70,
        getting_the_call: 85,
        site_fundamentals: 82,
        content_and_proof: 72,
        supporting_content: 68,
        social_and_video: 76,
      }
    : {
        service_pages: 28,
        service_area: 0,
        getting_the_call: 48,
        site_fundamentals: 52,
        content_and_proof: 30,
        supporting_content: 24,
        social_and_video: 40,
      }
  const included = CATS.reduce((n, [k, , w]) => n + (scores[k] != null ? w : 0), 0)
  const score = Math.round(CATS.reduce((n, [k, , w]) => n + w * (scores[k] ?? 0), 0) / included)
  const categories = CATS.map(([key, label, weight]) => {
    const s = scores[key]
    return s == null
      ? { key, label, weight, score: null, grade: null, pointsLost: null, excluded: true }
      : {
          key,
          label,
          weight,
          score: s,
          grade: grade(s),
          pointsLost: Math.round(((weight * 100) / included) * (100 - s)) / 100,
          excluded: false,
        }
  })
  const topIssues: OverviewSection['topIssues'] = strong
    ? [
        {
          category: 'service_area',
          title: 'Only 4 city pages',
          detail: 'Patients in other nearby towns cannot find a page built for their search.',
        },
        {
          category: 'service_pages',
          title: 'Hormone Replacement pages are thin',
          detail: '1 of 3 expected pages; misses 6 of 9 patient questions.',
        },
      ]
    : [
        {
          category: 'service_pages',
          title: 'Only 3 of 70 expected treatment pages exist',
          detail:
            'Botox, fillers, IV therapy and weight loss are each covered by a single thin page, so most treatment searches never reach this clinic.',
        },
        {
          category: 'service_area',
          title: 'No city or service area pages',
          detail: 'Patients in nearby towns cannot find a page built for their search.',
        },
        {
          category: 'getting_the_call',
          title: 'No online booking found',
          detail: 'After hours visitors cannot book without calling, so many simply leave.',
        },
        {
          category: 'content_and_proof',
          title: 'No before and after gallery',
          detail: 'Patients choosing an elective treatment want to see real results first.',
        },
        {
          category: 'supporting_content',
          title: 'Only 1 blog post in the last 12 months',
          detail: 'Regular posts answer the questions patients search before booking.',
        },
        {
          category: 'site_fundamentals',
          title: 'No LocalBusiness schema',
          detail: 'Google gets no structured signal for the clinic name, address and hours.',
        },
      ]
  const reasons = strong ? [] : ['No Google Business Profile found']
  return {
    score,
    grade: grade(score),
    provisional: reasons.length > 0,
    provisionalReasons: reasons,
    categories,
    topIssues,
    issueCount: strong ? 3 : 14,
    warningCount: strong ? 6 : 9,
    summaryText: `${domain}: ${score}/100 (${grade(score)}). Top issues: ${topIssues
      .slice(0, 3)
      .map((i) => i.title)
      .join('; ')}.${reasons.length ? ` Provisional: ${reasons.join(', ')}.` : ''}`,
  }
}

const TRACE_LABEL: Record<string, string> = {
  home: 'Fetch home page',
  analyze: 'Analyse home page',
  menu: 'Read the site menu',
  map: 'Find pages',
  pick: 'Choose pages to read',
  scrape: 'Read pages',
  enrich: 'Build site facts',
  ai: 'AI page analysis',
  gbp: 'Google Business Profile',
  psi: 'PageSpeed',
  score: 'Score the audit',
  final: 'Audit finished',
}

/** The run log the backend would have written `elapsed` ms after the audit started. */
export function mockTrace(
  domain: string,
  elapsed: number,
  fails: boolean,
  startedAt: Date,
): TraceEvent[] {
  const base = `https://${domain}`
  const picked = [
    '/services/botox',
    '/services/fillers',
    '/services/iv-therapy',
    '/services/weight-loss',
    '/locations/austin',
    '/before-and-after',
    '/about',
    '/faq',
    '/blog/botox-aftercare',
  ].map((p) => base + p)
  const group = (name: string, from: number, to: number, found: number) => ({
    name,
    found,
    picked: picked.slice(from, to),
    skipped: found - (to - from),
  })
  type Step = {
    id: string
    start: number
    end: number
    status?: TraceEvent['status']
    run?: Record<string, unknown>
    detail: Record<string, unknown>
  }
  const steps: Step[] = [
    { id: 'home', start: 0, end: 500, detail: { via: 'direct', url: `${base}/`, size: 48213 } },
    { id: 'analyze', start: 500, end: 900, detail: {} },
    { id: 'menu', start: 900, end: 1200, detail: { links: 17, services: 9 } },
    fails
      ? { id: 'map', start: 900, end: 1900, status: 'failed', detail: { error: 'HTTP 402' } }
      : { id: 'map', start: 900, end: 1900, detail: { count: 142 } },
    { id: 'psi', start: 900, end: 4000, detail: { mobile: 64, desktop: 88 } },
  ]
  if (!fails) {
    steps.push(
      {
        id: 'pick',
        start: 1900,
        end: 1900,
        detail: {
          total: picked.length,
          groups: [
            group('service', 0, 4, 9),
            group('city', 4, 5, 1),
            group('proof', 5, 6, 1),
            group('trust', 6, 8, 2),
            group('blog', 8, 9, 1),
          ],
        },
      },
      {
        id: 'scrape',
        start: 1900,
        end: 3700,
        run: { total: picked.length },
        detail: { ok: picked.length - 1, failed: 1 },
      },
      ...picked.map((url, i) => ({
        id: `page:${url}`,
        start: 1900 + Math.floor(i / 4) * 600,
        end: 2500 + Math.floor(i / 4) * 600,
        status: (i === 6 ? 'failed' : 'done') as TraceEvent['status'],
        detail: { url },
      })),
      { id: 'enrich', start: 3700, end: 4000, detail: { pages: picked.length } },
      { id: 'ai', start: 4000, end: 5000, detail: { pages: picked.length } },
      { id: 'gbp', start: 5000, end: 5600, detail: { matched: true } },
    )
  }
  const scored = mockOverview(domain)
  steps.push({
    id: 'score',
    start: 5600,
    end: 6000,
    detail: { score: scored.score, grade: scored.grade },
  })
  const out: TraceEvent[] = []
  const at = (ms: number) => new Date(startedAt.getTime() + ms).toISOString()
  for (const s of steps) {
    const label = s.id.startsWith('page:')
      ? new URL(s.id.slice(5)).pathname
      : (TRACE_LABEL[s.id] ?? s.id)
    if (elapsed >= s.start && elapsed < s.end) {
      out.push({
        id: s.id,
        status: 'running',
        label,
        ms: null,
        at: at(s.start),
        detail: s.run ?? {},
      })
    } else if (elapsed >= s.end) {
      out.push({
        id: s.id,
        status: s.status ?? 'done',
        label,
        ms: s.end - s.start,
        at: at(s.end),
        detail: s.detail,
      })
    }
  }
  if (elapsed >= 6000) {
    out.push({
      id: 'final',
      status: 'done',
      label: TRACE_LABEL.final ?? 'final',
      ms: null,
      at: at(6000),
      detail: { outcome: fails ? 'partial' : 'ready' },
    })
  }
  return out.sort((a, b) => a.at.localeCompare(b.at))
}

export function buildAudit(id: string, domain: string, url: string, startedAt: Date): Audit {
  const strong = domain === STRONG_DOMAIN
  const svc = services(domain, strong)
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
    trace: mockTrace(domain, Number.POSITIVE_INFINITY, false, startedAt),
    overview: mockOverview(domain),
    business: {
      gbp: strong
        ? {
            matched: true,
            matchReason: 'phone + domain match',
            matchReasons: ['website address', 'phone number'],
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
        desktop: {
          performance: strong ? 94 : 72,
          seo: strong ? 96 : 84,
          accessibility: strong ? 90 : 76,
          bestPractices: strong ? 96 : 83,
          lcpMs: strong ? 1100 : 2900,
          cls: strong ? 0.01 : 0.12,
        },
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
