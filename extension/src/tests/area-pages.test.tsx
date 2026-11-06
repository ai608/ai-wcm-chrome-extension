import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { buildAudit } from '@/lib/api/mock/research-fixtures'
import type { Audit } from '@/lib/api/research-types'

afterEach(cleanup)

function withAreas(areas: NonNullable<Audit['site']>['cities']['areas']): Audit {
  const audit = buildAudit('aud_test', 'example.com', 'https://example.com/', new Date())
  if (!audit.site) throw new Error('fixture')
  return { ...audit, site: { ...audit.site, cities: { ...audit.site.cities, areas } } }
}

async function openCities(audit: Audit) {
  vi.stubGlobal('browser', fakeBrowser)
  const { SiteTab } = await import('@/components/research/SiteTab')
  if (!audit.site) throw new Error('fixture')
  render(<SiteTab audit={audit} site={audit.site} />)
  fireEvent.click(screen.getByText('Cities'))
}

const AREAS: NonNullable<Audit['site']>['cities']['areas'] = [
  {
    name: 'Tampa',
    status: 'covered',
    pages: ['https://example.com/tampa/'],
    issues: [],
    duplicateOf: null,
  },
  {
    name: 'Sarasota',
    status: 'needs_work',
    pages: ['https://example.com/sarasota/'],
    issues: ['thin', 'duplicate'],
    duplicateOf: 'Tampa',
  },
  { name: 'Ocala', status: 'mentioned', pages: [], issues: [], duplicateOf: null },
  { name: 'Orlando', status: 'missing', pages: [], issues: [], duplicateOf: null },
]

describe('area pages in the Cities view', () => {
  it('shows each claimed area with its status and what is wrong', async () => {
    await openCities(withAreas(AREAS))
    expect(screen.getByText('Has its own page')).toBeDefined()
    expect(
      screen.getByText("Page needs work: thin (under 300 words), copies Tampa's page"),
    ).toBeDefined()
    expect(screen.getByText('Named in the text, no page of its own')).toBeDefined()
    expect(screen.getByText('No page, not mentioned elsewhere')).toBeDefined()
  })

  it('still lists claimed-but-unbuilt areas for an audit saved before areas existed', async () => {
    await openCities(withAreas(undefined))
    expect(screen.getByText('Claimed but no page')).toBeDefined()
  })

  it('puts each problem in the gap list', async () => {
    const { gapInventory } = await import('@/components/research/SiteTab')
    const items = gapInventory(withAreas(AREAS))
      .filter((g) => g.area === 'Cities')
      .map((g) => g.item)
    expect(items).toContain("Sarasota page: thin (under 300 words), copies Tampa's page")
    expect(items).toContain('Ocala (mentioned, no page of its own)')
    expect(items).toContain('Orlando (claimed, no page)')
    expect(items.some((i) => i.startsWith('Tampa'))).toBe(false)
  })
})
