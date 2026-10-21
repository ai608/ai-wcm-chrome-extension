import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { ApiError } from '@/lib/api/errors'
import { buildAudit } from '@/lib/api/mock/research-fixtures'
import type { Audit } from '@/lib/api/research-types'

vi.mock('@/lib/messaging', async () => {
  const api = await import('@/lib/api/mock/handlers')
  const opened: unknown[] = []
  return {
    __opened: opened,
    call: async (key: string, d: Record<string, unknown> = {}) => {
      const a = d.auditId as string
      const map: Record<string, () => unknown> = {
        getLatestAudit: () => api.getLatestAudit(d.domain as string),
        startAudit: () => api.startAudit(d.url as string, d.force as boolean | undefined),
        getAudit: () => api.getAudit(a),
        runDomainOverview: () => api.runDomainOverview(a),
        runLocalCompetitors: () =>
          api.runLocalCompetitors(a, d.query as string, d.location as string),
        runAiVisibility: () => api.runAiVisibility(a, d.prompts as string[]),
        getReport: () => api.getReport(a),
        sendReport: () => api.sendReport(a, d.email as string, d.note as string),
        getContactResearch: () => api.getContactResearch(d.contactId as string),
        startContactResearch: () =>
          api.startContactResearch(d.contactId as string, d.force as boolean),
        openReport: () => opened.push(d),
      }
      return map[key]?.()
    },
  }
})

const full = (domain: string): Audit =>
  buildAudit('aud_test', domain, `https://${domain}/`, new Date())

beforeEach(async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
  fakeBrowser.reset()
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn(async () => {}) },
    configurable: true,
  })
  const { __resetMock } = await import('@/lib/api/mock/handlers')
  __resetMock()
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
  const { usePanelStore } = await import('@/stores/panel-store')
  usePanelStore.setState({ researchSubTab: {}, pendingConfirm: null, researchTab: 'overview' })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('Research Mode', () => {
  it('empty state -> run audit -> sections fill in progressively', async () => {
    const { Providers } = await import('@/app/providers')
    const { default: ResearchMode } = await import('@/components/research/ResearchMode')
    render(
      <Providers>
        <ResearchMode
          tab={{
            tabId: 1,
            url: 'https://example.com/',
            kind: 'website',
            origin: 'https://example.com',
            domain: 'example.com',
          }}
        />
      </Providers>,
    )
    const run = await screen.findByRole('button', { name: 'Run audit' })
    fireEvent.click(run)
    // progressive: checklist first
    await screen.findByText('Running audit…', undefined, { timeout: 3000 })
    // finally the F-grade fixture
    await screen.findByText('32 / 100', undefined, { timeout: 12000 })
    expect(screen.getByText(/Provisional/)).toBeDefined()
    expect(screen.getByText(/14 issues \+ 9 warn/)).toBeDefined()
    fireEvent.click(screen.getByText('Generate prospect report (PDF)'))
  }, 20000)

  it('blocked.example shows a friendly error', async () => {
    const { Providers } = await import('@/app/providers')
    const { default: ResearchMode } = await import('@/components/research/ResearchMode')
    render(
      <Providers>
        <ResearchMode
          tab={{
            tabId: 1,
            url: 'https://blocked.example/',
            kind: 'website',
            origin: 'https://blocked.example',
            domain: 'blocked.example',
          }}
        />
      </Providers>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Run audit' }))
    await screen.findByText('This address can’t be audited.')
  })
})

describe('Overview', () => {
  it('encodes quick-tool urls', async () => {
    const { quickToolLinks } = await import('@/components/research/OverviewTab')
    const links = quickToolLinks('https://example.com/a b?x=1&y=2')
    expect(links[0]?.href).toBe('https://example.com/robots.txt')
    expect(links[1]?.href).toBe('https://example.com/sitemap.xml')
    expect(links[2]?.href).toBe(
      'https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fexample.com%2Fa%20b%3Fx%3D1%26y%3D2',
    )
    expect(links[3]?.href).toContain('rich-results?url=https%3A%2F%2F')
  })

  it('send report: confirm, success and rejected email', async () => {
    const { Providers } = await import('@/app/providers')
    const { OverviewTab } = await import('@/components/research/OverviewTab')
    const api = await import('@/lib/api/mock/handlers')
    const seeded = await api.startAudit('https://example.com/')
    const audit = { ...full('example.com'), id: seeded.id }
    render(
      <Providers>
        <OverviewTab audit={audit} />
      </Providers>,
    )
    const email = screen.getByLabelText('Email')
    fireEvent.change(email, { target: { value: 'bounce@clinic.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(screen.getByText('Send the report to bounce@clinic.com?')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText('Email address rejected')

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'owner@glow.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText(/email ✓ · Slack ✓/)
    expect(ApiError).toBeDefined()
  })

  it('copies the audit summary', async () => {
    const { Providers } = await import('@/app/providers')
    const { OverviewTab } = await import('@/components/research/OverviewTab')
    const audit = full('example.com')
    render(
      <Providers>
        <OverviewTab audit={audit} />
      </Providers>,
    )
    fireEvent.click(screen.getByText('Copy audit summary'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(audit.overview?.summaryText)
  })
})

describe('On-Page and Site', () => {
  it('on-page: images filter shows only missing alt', async () => {
    const { OnPageTab } = await import('@/components/research/OnPageTab')
    const audit = full('example.com')
    if (!audit.onPage) throw new Error('fixture')
    render(<OnPageTab audit={audit} onPage={audit.onPage} />)
    fireEvent.click(screen.getByRole('button', { name: 'Images' }))
    expect(screen.queryAllByText('MISSING ALT').length).toBe(2)
    expect(screen.queryByText('Our team')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Missing alt' }))
    expect(screen.queryByText('Our team')).toBeNull()
    expect(screen.getByText('Export 2 images to CSV')).toBeDefined()
  })

  it('site: services accordion lists present and missing topics', async () => {
    const { SiteTab } = await import('@/components/research/SiteTab')
    const audit = full('example.com')
    if (!audit.site) throw new Error('fixture')
    const { clusterPagesFound: f, clusterPagesExpected: e } = audit.site.services
    render(<SiteTab audit={audit} site={audit.site} />)
    expect(screen.getByText(`${f}/${e}`)).toBeDefined()
    fireEvent.click(screen.getByText('IV Therapy'))
    expect(screen.getByText('✓ Hangover IV')).toBeDefined()
    expect(screen.getByText('✗ NAD+ IV')).toBeDefined()
  })

  it('gap inventory lists missing items across areas', async () => {
    const { gapInventory } = await import('@/components/research/SiteTab')
    const areas = new Set(gapInventory(full('example.com')).map((g) => g.area.split(':')[0]))
    expect(areas).toEqual(new Set(['Services', 'Cities', 'Proof', 'Trust', 'Schema', 'Convert']))
  })
})

describe('On-demand cards', () => {
  it('renders not_run, running, failed and ready states', async () => {
    const { Providers } = await import('@/app/providers')
    const { ResearchSubTabs } = await import('@/components/research/ResearchSubTabs')
    const base = full('glowaesthetics.com')
    const r = base.research
    if (!r) throw new Error('fixture')
    const view = (domainOverview: NonNullable<Audit['research']>['domainOverview']) =>
      render(
        <Providers>
          <ResearchSubTabs audit={{ ...base, research: { ...r, domainOverview } }} />
        </Providers>,
      )
    const a = view({ state: 'not_run', data: null, error: null, ranAt: null })
    expect(screen.getByText('Pull domain overview')).toBeDefined()
    a.unmount()
    const b = view({ state: 'running', data: null, error: null, ranAt: null })
    expect(screen.getByText('Running…')).toBeDefined()
    b.unmount()
    const c = view({ state: 'failed', data: null, error: 'Ahrefs limit', ranAt: null })
    expect(screen.getByText('Ahrefs limit')).toBeDefined()
    c.unmount()
    view({
      state: 'ready',
      error: null,
      ranAt: null,
      data: {
        domainRating: 38,
        organicTraffic: 2400,
        organicKeywords: 640,
        referringDomains: 96,
        backlinks: 1800,
        topKeywords: [{ keyword: 'med spa austin', position: 6, volume: 1900, url: null }],
      },
    })
    expect(screen.getByText('38')).toBeDefined()
    expect(screen.getByText('med spa austin')).toBeDefined()
  })
})

describe('Call Mode Research tab', () => {
  async function renderTab(id: string) {
    const { Providers } = await import('@/app/providers')
    const { default: ResearchTab } = await import('@/components/research/ResearchTab')
    return render(
      <Providers>
        <ResearchTab contactId={id} />
      </Providers>,
    )
  }

  it('no_website', async () => {
    await renderTab('c_vital')
    await screen.findByText('This contact has no website in GHL.')
  })

  it('ready for c_glow with cards', async () => {
    await renderTab('c_glow')
    await screen.findByText('Glow Aesthetics Med Spa', undefined, { timeout: 8000 })
    expect(screen.getByText('Refresh research')).toBeDefined()
  }, 12000)

  it('shows on-demand competitors for the active contact', async () => {
    await renderTab('c_glow')
    fireEvent.click(await screen.findByRole('button', { name: 'Find competitors' }))
    await screen.findByText(/This clinic/, undefined, { timeout: 12000 })
  }, 16000)

  it('run research for c_peak', async () => {
    await renderTab('c_peak')
    fireEvent.click(await screen.findByRole('button', { name: 'Run research' }))
    await waitFor(() => expect(screen.getByText('Refresh research')).toBeDefined())
  })
})

describe('Report page', () => {
  it('renders the report and hides the toolbar when printing', async () => {
    const api = await import('@/lib/api/mock/handlers')
    const seeded = await api.startAudit('https://example.com/')
    window.history.pushState({}, '', `/report.html?audit=${seeded.id}`)
    const { authUserItem } = await import('@/lib/storage')
    await authUserItem.setValue({
      id: 'u',
      email: 'a@b.c',
      fullName: 'Sam',
      role: 'user',
      hasExtensionAccess: true,
    })
    const { Providers } = await import('@/app/providers')
    const { ReportPage } = await import('@/components/report/ReportPage')
    const { container } = render(
      <Providers>
        <ReportPage />
      </Providers>,
    )
    await screen.findByText('Website & Local Visibility Report', undefined, { timeout: 5000 })
    expect(container.querySelector('.print\\:hidden')).not.toBeNull()
    expect(screen.getByText('Save as PDF').closest('.print\\:hidden')).not.toBeNull()
  })
})
