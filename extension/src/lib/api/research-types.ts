export type SectionKey =
  | 'overview'
  | 'business'
  | 'on_page'
  | 'schema'
  | 'site'
  | 'convert'
  | 'research'
export type SectionState = 'pending' | 'running' | 'ready' | 'failed' | 'skipped'
export type Grade = 'A' | 'B' | 'C' | 'D' | 'F'
export type CheckStatus = 'ok' | 'warn' | 'fail' | 'info'
export type CategoryKey =
  | 'gbp'
  | 'reviews'
  | 'service_pages'
  | 'service_area'
  | 'getting_the_call'
  | 'site_fundamentals'
  | 'content_proof'
  | 'supporting_content'
  | 'social_video'

export interface OverviewSection {
  score: number
  grade: Grade
  provisional: boolean
  categories: { key: CategoryKey; label: string; grade: Grade; score: number }[]
  topIssues: { category: CategoryKey; title: string; detail: string }[]
  issueCount: number
  warningCount: number
  summaryText: string
}

export interface BusinessSection {
  gbp: {
    matched: boolean
    matchReason: string | null
    name: string | null
    verified: boolean | null
    primaryCategory: string | null
    categories: string[]
    rating: number | null
    reviewCount: number | null
    address: string | null
    phone: string | null
    mapsUrl: string | null
    lat: number | null
    lng: number | null
    websiteLinksToGbp: boolean
    reviewLinkOnSite: boolean
  } | null
  company: {
    name: string | null
    industry: string | null
    employeeCount: number | null
    linkedinUrl: string | null
    foundedYear: number | null
    technologies: string[]
  } | null
  socials: {
    network: 'facebook' | 'instagram' | 'tiktok' | 'youtube' | 'linkedin' | 'x'
    url: string
  }[]
  nap: {
    name: string | null
    address: string | null
    phone: string | null
    consistentWithGbp: boolean | null
  }
}

export interface OnPageSection {
  essentials: { key: string; label: string; value: string; status: CheckStatus; note?: string }[]
  headings: { h1Count: number; outline: { level: 1 | 2 | 3 | 4 | 5 | 6; text: string }[] }
  links: {
    internal: number
    external: number
    nofollow: number
    items: { href: string; text: string; kind: 'internal' | 'external'; nofollow: boolean }[]
  }
  images: {
    total: number
    missingAlt: number
    lazy: number
    items: { src: string; alt: string | null; width: number | null; height: number | null }[]
  }
  pagespeed: {
    mobilePerformance: number | null
    seo: number | null
    accessibility: number | null
    bestPractices: number | null
    lcpMs: number | null
    cls: number | null
  } | null
}

export interface SchemaSection {
  jsonLdCount: number
  parseErrors: number
  hasLocalBusiness: boolean
  hasFaqPage: boolean
  hasReviewMarkup: boolean
  blocks: { type: string; presentProps: string[]; missingRecommended: string[] }[]
  raw: string
}

export interface SiteSection {
  platform: { name: string | null; detail: string | null }
  pagesCrawled: number
  services: {
    clusterPagesFound: number
    clusterPagesExpected: number
    clusters: {
      service: string
      found: number
      expected: number
      pages: string[]
      topicsPresent: string[]
      topicsMissing: string[]
    }[]
  }
  cities: {
    pagesFound: number
    hubPage: boolean
    cityPages: string[]
    claimedNotBuilt: string[]
  }
  proof: {
    beforeAfterGallery: boolean
    testimonialPages: number
    reviewsPage: boolean
    caseStudyPages: number
    videoTestimonials: boolean
  }
  blog: {
    url: string | null
    postCount: number
    lastPostAt: string | null
    postsLast6Months: number
    postsLast12Months: number
    linksToServices: boolean
    posts: { url: string; title: string; publishedAt: string | null }[]
  }
  trust: { key: string; label: string; status: 'found' | 'missing'; url: string | null }[]
}

export interface ConvertSection {
  bookingPlatform: string | null
  onlineBooking: boolean
  phoneInHeader: boolean
  clickToCall: boolean
  formsCount: number
  chatWidget: string | null
  ctaAboveFold: boolean
  offersOrSpecials: boolean
  financingMentioned: boolean
  textUs: boolean
  checks: { key: string; label: string; status: CheckStatus; note?: string }[]
}

export type OnDemand<T> = {
  state: 'not_run' | 'running' | 'ready' | 'failed'
  data: T | null
  error: string | null
  ranAt: string | null
}

export interface DomainOverview {
  domainRating: number | null
  organicTraffic: number | null
  organicKeywords: number | null
  referringDomains: number | null
  backlinks: number | null
  topKeywords: { keyword: string; position: number; volume: number | null; url: string | null }[]
}

export interface LocalCompetitors {
  query: string
  location: string
  items: {
    rank: number
    name: string
    rating: number | null
    reviewCount: number | null
    website: string | null
    isThisBusiness: boolean
  }[]
}

export interface AiVisibility {
  prompts: string[]
  engines: { engine: string; cited: boolean; citedBusinesses: string[]; answerExcerpt: string }[]
}

export interface ResearchSection {
  domainOverview: OnDemand<DomainOverview>
  localCompetitors: OnDemand<LocalCompetitors>
  aiVisibility: OnDemand<AiVisibility>
}

export interface Audit {
  id: string
  url: string
  domain: string
  status: 'queued' | 'running' | 'ready' | 'partial' | 'failed'
  error: string | null
  createdAt: string
  finishedAt: string | null
  sectionState: Record<SectionKey, SectionState>
  overview: OverviewSection | null
  business: BusinessSection | null
  onPage: OnPageSection | null
  schema: SchemaSection | null
  site: SiteSection | null
  convert: ConvertSection | null
  research: ResearchSection | null
}

export interface Report {
  audit: Audit
  preparedFor: string
  preparedBy: string
  generatedAt: string
  intro: string
}

export interface SendReportResult {
  emailSent: boolean
  slackSent: boolean
  ghlContactId: string | null
}

export interface ContactResearch {
  audit: Audit | null
  reason?: 'no_website'
}

export function auditBusy(a: Audit | null | undefined): boolean {
  if (!a) return false
  if (a.status === 'queued' || a.status === 'running') return true
  const r = a.research
  return (
    r != null &&
    (r.domainOverview.state === 'running' ||
      r.localCompetitors.state === 'running' ||
      r.aiVisibility.state === 'running')
  )
}
