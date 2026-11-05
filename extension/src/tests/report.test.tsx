import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { Body } from '@/components/report/ReportPage'
import { buildAudit, PENDING_OVERVIEW } from '@/lib/api/mock/research-fixtures'
import type { Report } from '@/lib/api/research-types'

vi.mock('@/hooks/use-auth', () => ({ useAuth: () => ({ user: null, isLoading: false }) }))
vi.mock('@/hooks/research-queries', () => ({ useReport: () => ({}) }))
vi.mock('@/lib/messaging', () => ({ call: async () => null }))

function makeReport(): Report {
  const audit = buildAudit('aud_report', 'example.com', 'https://example.com/', new Date())
  if (audit.site) {
    audit.site = { ...audit.site, pagesCrawled: 1 }
  }
  return {
    audit,
    preparedFor: 'example.com',
    preparedBy: 'WCM · Sam',
    generatedAt: new Date().toISOString(),
    intro: 'Intro text.',
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

beforeEach(() => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  fakeBrowser.reset()
})

describe('ReportPage Body print output', () => {
  it('sets page 1 as the decision and lets later sections split', () => {
    const { container } = render(
      <div className="report-root">
        <Body report={makeReport()} />
      </div>,
    )
    expect(container.querySelector('.report-cover')).not.toBeNull()
    expect(container.querySelector('.report-offer')).not.toBeNull()
    expect(container.querySelector('.report-running')?.textContent).toContain('example.com')
    expect(container.querySelector('.report-table')).not.toBeNull()
    const header = container.querySelector('header')
    expect(header?.className).toContain('report-masthead')
    expect(header?.className).toContain('[print-color-adjust:exact]')
    const grade = container.querySelector('.report-grade-mark')
    expect(grade?.textContent).toBe('F')
    expect(grade?.className).toContain('[print-color-adjust:exact]')
    for (const section of container.querySelectorAll('section')) {
      expect(section.className).not.toContain('break-inside-avoid')
    }
    expect(container.querySelector('.report-row')).not.toBeNull()
    const headings = [...container.querySelectorAll('h2')].map((h) => h.textContent)
    const gaps = headings.indexOf('What’s costing them calls')
    const offer = headings.indexOf('How we fix it')
    const scoresHeading = headings.indexOf('Where the score comes from')
    const treatments = headings.indexOf('Treatment pages')
    expect(scoresHeading).toBeGreaterThan(-1)
    expect(scoresHeading).toBeLessThan(gaps)
    expect(gaps).toBeLessThan(offer)
    expect(offer).toBeLessThan(treatments)
    const why = screen.getAllByText(/Why this matters/)[0]
    const offerHeading = [...container.querySelectorAll('h2')].find(
      (h) => h.textContent === 'How we fix it',
    )
    if (!why || !offerHeading) throw new Error('offer block missing')
    expect(
      Boolean(offerHeading.compareDocumentPosition(why) & Node.DOCUMENT_POSITION_FOLLOWING),
    ).toBe(true)
    const issues = makeReport().audit.overview?.topIssues ?? []
    expect(issues.length).toBeGreaterThan(3)
    for (const i of issues) {
      expect(screen.getByText(i.title)).toBeDefined()
    }
    for (const i of issues) {
      expect(i.title).not.toContain('\u2014')
      expect(i.detail).not.toContain('\u2014')
      expect(i.title).not.toContain('needs attention')
    }
    expect(screen.getAllByText('Mentioned on home page').length).toBeGreaterThan(0)
    expect(screen.getByText(/Home page mentions only/)).toBeDefined()
    expect(screen.getByText(/Overall score: \d+ \/ 100/)).toBeDefined()
    expect(container.querySelectorAll('.report-grade-letter').length).toBeGreaterThan(0)
    expect(screen.queryByText('Treatment pages found')).toBeNull()
    expect(screen.getByRole('heading', { name: 'PageSpeed' })).toBeDefined()
    expect(screen.getByText('Mobile')).toBeDefined()
    expect(screen.getByText('Desktop')).toBeDefined()
    expect(screen.getAllByText('Performance')).toHaveLength(2)
  })

  it('leaves the score out while it is not computed yet', () => {
    const report = makeReport()
    report.audit.overview = structuredClone(PENDING_OVERVIEW)
    const { container } = render(<Body report={report} />)
    expect(container.textContent).not.toMatch(/\/ 100|None|null/)
    expect(screen.queryByText('Where the score comes from')).toBeNull()
  })

  it('marks excluded categories as not assessed', () => {
    render(<Body report={makeReport()} />)
    expect(screen.getAllByText('Not assessed')).toHaveLength(2)
    expect(screen.getByText(/Provisional: No Google Business Profile found/)).toBeDefined()
  })

  it('keeps the Google profile on one card', () => {
    const report = makeReport()
    const business = report.audit.business
    if (!business) throw new Error('business missing')
    business.gbp = {
      matched: true,
      matchReason: null,
      name: 'The Pur Health: Sabeen Munib, MD',
      verified: true,
      primaryCategory: 'Medical clinic',
      categories: [],
      rating: 4.8,
      reviewCount: 104,
      address: '114 Pacifica #280, Irvine, CA 92618',
      phone: '(949) 647-5234',
      mapsUrl: null,
      lat: null,
      lng: null,
      websiteLinksToGbp: true,
      reviewLinkOnSite: false,
    }
    const { container } = render(<Body report={report} />)
    const card = container.querySelector('.report-gbp')
    expect(card).not.toBeNull()
    expect(card?.querySelector('.report-list')).toBeNull()
    expect(card?.textContent).toContain('The Pur Health: Sabeen Munib, MD')
    expect(card?.textContent).toContain('Medical clinic')
    expect(card?.textContent).toContain('4.8')
    expect(card?.textContent).toContain('104 Google reviews')
    expect(card?.textContent).toContain('Claimed')
    expect(card?.textContent).toContain('Site links to profile')
    expect(card?.textContent).toContain('No review link on site')
  })
})
