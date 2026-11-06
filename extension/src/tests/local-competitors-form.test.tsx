import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { buildAudit, competitorsFixture } from '@/lib/api/mock/research-fixtures'
import type { Audit } from '@/lib/api/research-types'

const calls: { key: string; data: Record<string, unknown> }[] = []
vi.mock('@/lib/messaging', () => ({
  call: async (key: string, data: Record<string, unknown> = {}) => {
    calls.push({ key, data })
    return null
  },
}))

function auditWithGbp(lat: number | null, lng: number | null): Audit {
  const a = buildAudit('aud_lc', 'glow.com', 'https://glow.com/', new Date())
  if (!a.business) throw new Error('fixture has no business section')
  a.business.gbp = {
    ...a.business.gbp,
    matched: true,
    address: '12 Main St, Austin, TX 78701',
    lat,
    lng,
  } as never
  return a
}

async function form(audit: Audit) {
  const { Providers } = await import('@/app/providers')
  const { LocalCompetitorsForm } = await import('@/components/research/ResearchSubTabs')
  return render(
    <Providers>
      <LocalCompetitorsForm audit={audit} />
    </Providers>,
  )
}

beforeEach(async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  fakeBrowser.reset()
  calls.length = 0
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('Local competitors form', () => {
  it('clinic coordinates known: location is prefilled with the clinic address and still searches around the clinic', async () => {
    await form(auditWithGbp(30.27, -97.74))
    expect((screen.getByLabelText('Location') as HTMLInputElement).value).toBe(
      '12 Main St, Austin, TX 78701',
    )
    expect(screen.getByText(/within 8 km of the clinic/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Find competitors' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]?.data.location).toBe('')
  })

  it('a typed place is sent as typed', async () => {
    await form(auditWithGbp(30.27, -97.74))
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Dallas, TX' } })
    fireEvent.click(screen.getByRole('button', { name: 'Find competitors' }))
    await waitFor(() => expect(calls[0]?.data.location).toBe('Dallas, TX'))
  })

  it('no coordinates: the city from the address is the default, no hint', async () => {
    await form(auditWithGbp(null, null))
    expect((screen.getByLabelText('Location') as HTMLInputElement).value).toBe('Austin, TX')
    expect(screen.queryByText(/within 8 km of the clinic/)).toBeNull()
  })
})

describe('Competitor list', () => {
  it('says the rank is approximate and reads well for a search around the clinic', async () => {
    const { CompetitorList } = await import('@/components/research/ResearchSubTabs')
    const data = { ...competitorsFixture('med spa'), location: 'within 8 km of 12 Main St' }
    render(<CompetitorList data={data} />)
    expect(screen.getByText(/med spa” within 8 km of 12 Main St/)).toBeTruthy()
    expect(screen.getByText(/rank is approximate/)).toBeTruthy()
  })

  it('a typed city still reads "in <city>"', async () => {
    const { CompetitorList } = await import('@/components/research/ResearchSubTabs')
    render(<CompetitorList data={competitorsFixture('med spa', 'Dallas, TX')} />)
    expect(screen.getByText(/med spa” in Dallas, TX/)).toBeTruthy()
  })

  it('opens the listing site and skips a row with no website', async () => {
    const { CompetitorList } = await import('@/components/research/ResearchSubTabs')
    const data = competitorsFixture()
    data.items[0]!.website = 'javascript:alert(1)'
    render(<CompetitorList data={data} links />)
    const links = screen.getAllByRole('link', { name: 'Visit site' })
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      'https://skinlab.example/',
      'https://glowaesthetics.com/',
    ])
    expect(links.every((link) => link.getAttribute('target') === '_blank')).toBe(true)
  })
})
