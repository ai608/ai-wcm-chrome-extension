import { ApiError } from '@/lib/api/errors'
import {
  aiVisibilityFixture,
  buildAudit,
  competitorsFixture,
  domainOverviewFixture,
  STRONG_DOMAIN,
} from '@/lib/api/mock/research-fixtures'
import type {
  Audit,
  ContactResearch,
  OnDemand,
  Report,
  SectionKey,
  SendReportResult,
} from '@/lib/api/research-types'

interface Stored {
  full: Audit
  startedAt: number
  fails: boolean
  runs: Partial<Record<'domain' | 'local' | 'ai', { readyAt: number; data: unknown }>>
}

const audits = new Map<string, Stored>()
const byDomain = new Map<string, string>()

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
const latency = () => wait(300 + Math.random() * 300)

// ms after start at which each section becomes ready
const READY_AT: Record<SectionKey, number> = {
  on_page: 1000,
  research: 1000,
  schema: 1500,
  site: 3000,
  business: 4000,
  convert: 4500,
  overview: 5000,
}
const DONE_AT = 6000

function domainOf(url: string): string {
  let u: URL
  try {
    u = new URL(url)
  } catch {
    throw new ApiError(422, 'invalid_url', 'Enter a valid website address')
  }
  const host = u.hostname.toLowerCase().replace(/^www\./, '')
  if (host.startsWith('blocked.')) {
    throw new ApiError(422, 'url_not_allowed', 'This address can’t be audited')
  }
  return host
}

function od<T>(
  state: OnDemand<T>['state'],
  data: T | null = null,
  ranAt: string | null = null,
): OnDemand<T> {
  return { state, data, error: null, ranAt }
}

function view(s: Stored): Audit {
  const elapsed = Date.now() - s.startedAt
  const a = structuredClone(s.full)
  const keys = Object.keys(READY_AT) as SectionKey[]
  for (const k of keys) {
    const ready = elapsed >= READY_AT[k]
    if (k === 'site' && s.fails) {
      a.sectionState.site = ready ? 'failed' : elapsed > 1000 ? 'running' : 'pending'
      a.site = null
      continue
    }
    a.sectionState[k] = ready ? 'ready' : elapsed > READY_AT[k] - 1200 ? 'running' : 'pending'
    if (!ready) {
      const field = { on_page: 'onPage' }[k as 'on_page'] ?? k
      ;(a as unknown as Record<string, unknown>)[field] = null
    }
  }
  const done = elapsed >= DONE_AT
  a.status = done ? (s.fails ? 'partial' : 'ready') : 'running'
  a.finishedAt = done ? a.finishedAt : null
  if (a.research) {
    const r = s.runs
    const stateOf = (run: (typeof r)['domain']) =>
      !run ? null : Date.now() >= run.readyAt ? 'ready' : 'running'
    a.research.domainOverview = r.domain
      ? stateOf(r.domain) === 'ready'
        ? od('ready', r.domain.data as never, new Date().toISOString())
        : od('running')
      : od('not_run')
    a.research.localCompetitors = r.local
      ? stateOf(r.local) === 'ready'
        ? od('ready', r.local.data as never, new Date().toISOString())
        : od('running')
      : od('not_run')
    a.research.aiVisibility = r.ai
      ? stateOf(r.ai) === 'ready'
        ? od('ready', r.ai.data as never, new Date().toISOString())
        : od('running')
      : od('not_run')
  }
  return a
}

function create(url: string, startedAt = Date.now()): Stored {
  const domain = domainOf(url)
  const id = `aud_${domain}_${startedAt}`
  const s: Stored = {
    full: buildAudit(id, domain, url, new Date(startedAt)),
    startedAt,
    fails: domain === 'fail.example',
    runs: {},
  }
  audits.set(id, s)
  byDomain.set(domain, id)
  return s
}

function get(auditId: string): Stored {
  const s = audits.get(auditId)
  if (!s) throw new ApiError(404, 'audit_not_found', 'Audit not found')
  return s
}

export async function startAudit(url: string, force?: boolean): Promise<Audit> {
  await latency()
  const domain = domainOf(url)
  const existing = byDomain.get(domain)
  if (existing && !force) return view(get(existing))
  return view(create(url))
}

export async function getAudit(auditId: string): Promise<Audit> {
  await latency()
  return view(get(auditId))
}

export async function getLatestAudit(domain: string): Promise<Audit | null> {
  await latency()
  const id = byDomain.get(domain)
  return id ? view(get(id)) : null
}

function startRun(auditId: string, key: 'domain' | 'local' | 'ai', data: unknown): Audit {
  const s = get(auditId)
  s.runs[key] = { readyAt: Date.now() + 2000 + Math.random() * 2000, data }
  return view(s)
}

export async function runDomainOverview(auditId: string): Promise<Audit> {
  await latency()
  return startRun(
    auditId,
    'domain',
    domainOverviewFixture(get(auditId).full.domain === STRONG_DOMAIN),
  )
}

export async function runLocalCompetitors(
  auditId: string,
  query?: string,
  location?: string,
): Promise<Audit> {
  await latency()
  return startRun(auditId, 'local', competitorsFixture(query, location))
}

export async function runAiVisibility(auditId: string, prompts: string[]): Promise<Audit> {
  await latency()
  return startRun(
    auditId,
    'ai',
    aiVisibilityFixture(get(auditId).full.domain === STRONG_DOMAIN, prompts),
  )
}

export async function getReport(auditId: string): Promise<Report> {
  await latency()
  const audit = view(get(auditId))
  return {
    audit,
    preparedFor: audit.business?.gbp?.name ?? audit.domain,
    preparedBy: 'WCM · Sam Rivera',
    generatedAt: new Date().toISOString(),
    intro: `We reviewed ${audit.domain} the way a new patient would: searching for treatments, comparing clinics and deciding whether to book. This report shows where the site is winning and where patients are slipping away.`,
  }
}

export async function sendReport(
  auditId: string,
  email: string,
  note?: string,
): Promise<SendReportResult> {
  await wait(800)
  get(auditId)
  void note
  if (email.startsWith('bounce@')) {
    throw new ApiError(422, 'validation_error', 'Email address rejected')
  }
  return {
    emailSent: true,
    slackSent: true,
    ghlContactId: email.includes('glow') ? 'c_glow' : null,
  }
}

const contactAudit = new Map<string, string>()

export async function getContactResearch(contactId: string): Promise<ContactResearch> {
  await latency()
  if (contactId === 'c_vital') return { audit: null, reason: 'no_website' }
  if (contactId === 'c_glow' && !contactAudit.has(contactId)) {
    contactAudit.set(contactId, create(`https://${STRONG_DOMAIN}/`, Date.now() - 10_000).full.id)
  }
  const id = contactAudit.get(contactId)
  return { audit: id ? view(get(id)) : null }
}

export async function startContactResearch(
  contactId: string,
  force?: boolean,
): Promise<ContactResearch> {
  await latency()
  if (contactId === 'c_vital') return { audit: null, reason: 'no_website' }
  const existing = contactAudit.get(contactId)
  if (existing && !force) return { audit: view(get(existing)) }
  const url = contactId === 'c_glow' ? `https://${STRONG_DOMAIN}/` : 'https://peakchiro.example/'
  const s = create(url)
  contactAudit.set(contactId, s.full.id)
  return { audit: view(s) }
}

export function __resetResearchMock() {
  audits.clear()
  byDomain.clear()
  contactAudit.clear()
}
