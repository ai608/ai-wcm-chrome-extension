import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { buildAudit } from '@/lib/api/mock/research-fixtures'

const audit = (domain: string) => buildAudit('aud_op', domain, `https://${domain}/`, new Date())

beforeEach(async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
  fakeBrowser.reset()
  const { usePanelStore } = await import('@/stores/panel-store')
  usePanelStore.setState({ researchSubTab: {} })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('On-page checks', () => {
  it('opens on the summary with the score, counts and top fixes', async () => {
    const { OnPageTab } = await import('@/components/research/OnPageTab')
    const a = audit('weak.example')
    if (!a.onPage) throw new Error('fixture')
    render(<OnPageTab audit={a} onPage={a.onPage} />)
    expect(screen.getByText('52 / 100')).toBeDefined()
    expect(screen.getByText('Google is told to hide this page')).toBeDefined()
    expect(screen.getByText('Same title as 1 other page(s)')).toBeDefined()
    expect(screen.getByText('Provider credentials')).toBeDefined()
    expect(screen.getByText('None linked')).toBeDefined()
  })

  it('lists pages with issues first and shows a page’s issues when opened', async () => {
    const { OnPageTab } = await import('@/components/research/OnPageTab')
    const a = audit('weak.example')
    if (!a.onPage) throw new Error('fixture')
    render(<OnPageTab audit={a} onPage={a.onPage} />)
    fireEvent.click(screen.getByText('Pages'))
    expect(screen.getByText('/botox')).toBeDefined()
    expect(screen.queryByText('/iv-therapy')).toBeNull()
    fireEvent.click(screen.getByText(/All 2/))
    expect(screen.getByText('/iv-therapy')).toBeDefined()
    expect(screen.getByText('No main heading (H1)')).toBeDefined()
  })

  it('falls back to the old tabs when the audit has no per-page checks', async () => {
    const { OnPageTab } = await import('@/components/research/OnPageTab')
    const a = audit('weak.example')
    if (!a.onPage) throw new Error('fixture')
    const { summary: _s, pages: _p, ...old } = a.onPage
    render(<OnPageTab audit={a} onPage={old} />)
    expect(screen.queryByText('Summary')).toBeNull()
    expect(screen.getByText('Meta description')).toBeDefined()
  })

  it('shows missing required schema fields and the self-serving review warning', async () => {
    const { SchemaTab } = await import('@/components/research/SchemaTab')
    const a = audit('glowaesthetics.com')
    if (!a.schema) throw new Error('fixture')
    const schema = {
      ...a.schema,
      risks: ['self_serving_review'],
      blocks: [
        {
          type: 'LocalBusiness',
          presentProps: ['name'],
          missingRequired: ['address'],
          missingRecommended: ['geo'],
        },
      ],
    }
    render(<SchemaTab audit={a} schema={schema} />)
    expect(screen.getByText('missing address')).toBeDefined()
    expect(screen.getByText(/does not allow a business to give itself/)).toBeDefined()
  })

  it('says so when no important problem is found', async () => {
    const { Providers } = await import('@/app/providers')
    const { Summary } = await import('@/components/research/OnPageChecks')
    const a = audit('glowaesthetics.com')
    if (!a.onPage) throw new Error('fixture')
    render(
      <Providers>
        <Summary onPage={a.onPage} />
      </Providers>,
    )
    expect(screen.getByText('No important on-page problems found.')).toBeDefined()
  })
})
