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
  | 'google_business_profile'
  | 'reviews'
  | 'service_pages'
  | 'service_area'
  | 'getting_the_call'
  | 'site_fundamentals'
  | 'content_and_proof'
  | 'supporting_content'
  | 'social_and_video'

/**
 * One scored category. `weight` is missing on audits saved before the final weighted
 * score (home-page score, 2 categories); excluded categories have no score or grade.
 */
export interface OverviewCategory {
  key: CategoryKey
  label: string
  grade: Grade | null
  score: number | null
  weight?: number
  pointsLost?: number | null
  excluded?: boolean
}

/** `score` and `grade` stay null until the whole audit has finished. */
export interface OverviewSection {
  score: number | null
  grade: Grade | null
  provisional: boolean
  provisionalReasons?: string[]
  categories: OverviewCategory[]
  topIssues: { category: CategoryKey; title: string; detail: string }[]
  issueCount: number
  warningCount: number
  summaryText: string
}

/** Saved before the final weighted score: its categories carry no weight. */
export function isLegacyOverview(o: OverviewSection): boolean {
  return o.score != null && o.categories.length > 0 && o.categories.every((c) => c.weight == null)
}

export interface BusinessSection {
  gbp: {
    matched: boolean
    matchReason: string | null
    matchReasons?: string[]
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

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export interface OnPageIssue {
  key: string
  severity: Severity
  title: string
  detail: string
  url: string | null
}

export interface OnPageFix {
  key: string
  severity: Severity
  title: string
  detail: string
  count: number
  pages: string[]
}

export interface OnPagePage {
  url: string
  kind: string
  title: string
  titleLen: number
  metaDescription: string
  h1: string
  h1Count: number
  wordCount: number
  noindex: boolean
  canonical: { url: string | null; status: string }
  issues: OnPageIssue[]
}

/**
 * Real-visitor data from Chrome (CrUX), 75th percentile with Google's FAST/AVERAGE/SLOW verdict.
 * `source` says whether it is this page's or the whole site's. A small site has none (null).
 */
export interface PageField {
  source: 'url' | 'origin'
  lcpMs: number | null
  lcp: string | null
  inpMs: number | null
  inp: string | null
  cls: number | null
  clsCategory: string | null
}

/** One internal link that was checked: where it ends up after redirects. */
export interface LinkRow {
  url: string
  status: number | null
  hops: number
  final: string
  foundOn: string | null
}

export interface OnPageSection {
  /** Absent on audits saved before the per-page checks. */
  pages?: OnPagePage[]
  duplicates?: { titles: string[][]; descriptions: string[][]; text: string[][] }
  siteIssues?: OnPageIssue[]
  trust?: {
    credentialsPages: string[]
    reviewedByPages: string[]
    datedPages: string[]
    disclaimerPages: string[]
    referenceLinks: number
    hasTerms: boolean
  }
  local?: { mapEmbed: boolean; hoursText: boolean }
  orphans?: string[]
  access?: {
    robots: {
      state: 'ok' | 'missing' | 'error'
      blocksSite: boolean
      blockedPages: string[]
      blockedAssets: number
      /** Crawlers robots.txt singles out: Bingbot and AI crawlers. Absent on older audits. */
      blockedBots?: string[]
    }
    sitemap: {
      declared: boolean
      files: { url: string; state: string; urls: number }[]
      urls: number
      missingPages: string[]
      badUrls: string[]
      blocked: number
    }
  }
  /** Absent on audits saved before the link and redirect checks. */
  linkCheck?: { checked: number; broken: LinkRow[]; chains: LinkRow[]; redirects: LinkRow[] }
  structure?: {
    deep: string[]
    noBookingLink: string[]
    noRelatedLinks: string[]
    maxDepth: number
  }
  /** The extra requests of the audit. `ran` is false for a site that blocks direct requests. */
  probes?: {
    ran: boolean
    checked: number
    timedOut: number
    hosts: { url: string; status: number | null; final: string | null; hops: number | null }[]
  }
  summary?: {
    score: number
    critical: number
    high: number
    medium: number
    low: number
    topFixes: OnPageFix[]
  }
  essentials: { key: string; label: string; value: string; status: CheckStatus; note?: string }[]
  headings: { h1Count: number; outline: { level: 1 | 2 | 3 | 4 | 5 | 6; text: string }[] }
  links: {
    internal: number
    external: number
    nofollow: number
    genericAnchorCount?: number
    emptyAnchorCount?: number
    notCrawlableCount?: number
    items: { href: string; text: string; kind: 'internal' | 'external'; nofollow: boolean }[]
  }
  images: {
    total: number
    missingAlt: number
    lazy: number
    badAlt?: number
    badNames?: number
    legacyFormat?: number
    firstImageLazy?: boolean
    noDimensions?: number
    cssBackgrounds?: number
    large?: { url: string; bytes: number }[]
    sizesChecked?: number
    items: { src: string; alt: string | null; width: number | null; height: number | null }[]
  }
  pagespeed: {
    mobilePerformance: number | null
    seo: number | null
    accessibility: number | null
    bestPractices: number | null
    lcpMs: number | null
    cls: number | null
    /** Whether touch targets are big enough, and zoom is allowed. null: not measured. */
    tapTargetsOk?: boolean | null
    zoomOk?: boolean | null
    /** Real-visitor data. null: Google has none for this site. Absent on older audits. */
    field?: PageField | null
    /** Absent on audits saved before desktop was measured; null when that call failed. */
    desktop?: {
      performance: number | null
      seo: number | null
      accessibility: number | null
      bestPractices: number | null
      lcpMs: number | null
      cls: number | null
    } | null
  } | null
}

export interface SchemaSection {
  jsonLdCount: number
  parseErrors: number
  hasLocalBusiness: boolean
  hasFaqPage: boolean
  hasReviewMarkup: boolean
  risks?: string[]
  localBusinessType?: string | null
  blocks: {
    type: string
    presentProps: string[]
    missingRequired?: string[]
    missingRecommended: string[]
  }[]
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
    datedPosts?: number
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
  /** `partial`: a full AI report that ended with too few good answers to trust the score. */
  state: 'not_run' | 'running' | 'ready' | 'partial' | 'failed'
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

/** One question asked to one engine. `excerpt` is the preview; `text` is the full reply. */
export interface AiAnswer {
  prompt: string
  ok: boolean
  mentioned: boolean
  linked: boolean
  competitors: string[]
  excerpt: string
  /** Absent on checks saved before the full reply was kept. */
  text?: string
  error: string | null
}

export interface AiEngineResult {
  engine: string
  model: string
  /** The clinic is named or linked in at least one answer. Kept for the report page. */
  cited: boolean
  mentioned: boolean
  /** A source link points at the clinic's own domain. */
  linked: boolean
  promptsMentioned: number
  promptsTotal: number
  promptsFailed: number
  citedBusinesses: string[]
  answerExcerpt: string
  error: string | null
  answers: AiAnswer[]
  /** Full report only: how often this engine named the clinic, with its 95% range. */
  mentionRate?: AiMentionRate
}

/** The clinic was named in `k` of `n` answers. `low`..`high` is the 95% range of the true rate. */
export interface AiMentionRate {
  k: number
  n: number
  rate: number
  low: number
  high: number
}

export interface AiBrandScore {
  VI: number
  perModel: Record<string, number>
  coverage: number
  citationRate: number
  sentiment: number
}

/** Scores of a full report. `visibilityIndex` is 0 to 100. `matrix` is engine > question index > 0..1. */
export interface AiReportMetrics {
  target: string
  visibilityIndex: number
  mentionRate: AiMentionRate
  shareOfVoice: Record<string, number>
  perBrand: Record<string, AiBrandScore>
  leaderboard: string[]
  gapVsTopCompetitor: number
  coverage: number
  citationRate: number
  sentimentIndex: number
  sentimentBreakdown: { positive: number; neutral: number; negative: number }
  matrix: Record<string, Record<string, number>>
  promptAnalytics: { promptId: number; avgVisibility: number; mentionRate: number }[]
}

export interface AiReportQuality {
  calls: number
  ok: number
  failed: number
  skipped: number
  successRate: number
  capped: boolean
  partialReason: string | null
  judgeFailed: number
}

export interface AiReportProgress {
  total: number
  asked: number
  failed: number
  judged: number
  /** Which step the bar counts. Older reports have neither this nor `readTotal`. */
  phase?: 'ask' | 'read'
  readTotal?: number
  costUsd: number
}

/** Step 1 of a full report: the written questions and how big the run would be. */
export interface AiQuestions {
  prompts: string[]
  source: 'llm' | 'llm+templates' | 'templates'
  engines: string[]
  runs: number
  maxQuestions: number
  maxCalls: number
}

/** One saved answer of a full report. */
export interface AiRunAnswer {
  prompt: number
  engine: string
  run: number
  ok: boolean
  text: string
  sources: string[]
  error: string | null
}

export interface AiRunAnswers {
  prompts: string[]
  items: AiRunAnswer[]
}

/**
 * `competitors` and `usage` arrive when the run ends. While it runs, only `log` is live.
 * `log` is folded by the server: one entry per step id, already the latest state.
 */
export interface AiVisibility {
  version: number
  /** Set on a full report (many questions, repeats, a score). Absent on the quick check. */
  kind?: 'full'
  runId?: string
  scoringVersion?: number
  progress?: AiReportProgress
  report?: AiReportMetrics
  quality?: AiReportQuality
  brand: string
  prompts: string[]
  engines: AiEngineResult[]
  competitors?: { source: 'local_competitors' | 'llm' | 'none'; names: string[] }
  /**
   * Run totals, judge call included. The input/output split is absent on checks saved before it
   * was kept. The per-engine breakdown lives in the `usage` log step.
   */
  usage?: {
    calls: number
    failed: number
    tokens: number
    promptTokens?: number
    completionTokens?: number
    costUsd: number
    ms: number
  }
  log: TraceEvent[]
}

export interface ResearchSection {
  domainOverview: OnDemand<DomainOverview>
  localCompetitors: OnDemand<LocalCompetitors>
  aiVisibility: OnDemand<AiVisibility>
}

export type TraceStatus = 'running' | 'done' | 'failed' | 'skipped'

/** One status change of one pipeline step. Fold by `id`: the last event wins. */
export interface TraceEvent {
  id: string
  status: TraceStatus
  label: string
  ms: number | null
  at: string
  detail: Record<string, unknown>
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
  trace: TraceEvent[]
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
