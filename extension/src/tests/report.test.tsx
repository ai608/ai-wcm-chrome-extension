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
  it('keeps colours, avoids clipping and uses plain issue copy', () => {
    const { container } = render(
      <div className="report-root print:px-[14mm]">
        <Body report={makeReport()} />
      </div>,
    )
    const root = container.querySelector('.report-root')
    expect(root).not.toBeNull()
    expect(root?.className).toContain('print:px-[14mm]')
    // Body stacks with margins (not flex gap) in print, so a section that
    // starts a new printed page keeps top spacing instead of touching the edge.
    const body = container.querySelector('.report-root > div')
    expect(body?.className).toContain('print:block')
    const header = container.querySelector('header')
    expect(header?.className).toContain('bg-primary')
    expect(header?.className).toContain('[print-color-adjust:exact]')
    const grade = screen.getByText('F')
    expect(grade.className).toContain('[print-color-adjust:exact]')
    expect(container.querySelector('section')?.className).toContain('break-inside-avoid')
    const issues = makeReport().audit.overview?.topIssues ?? []
    expect(issues.length).toBeGreaterThan(0)
    for (const i of issues) {
      expect(i.title).not.toContain('\u2014')
      expect(i.detail).not.toContain('\u2014')
      expect(i.title).not.toContain('needs attention')
    }
    expect(screen.getAllByText('Mentioned on home page').length).toBeGreaterThan(0)
    expect(screen.getByText(/Home page mentions only/)).toBeDefined()
    const scores = screen.getAllByText(/\/ 100 \(/)
    expect(scores.length).toBeGreaterThan(0)
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
})
