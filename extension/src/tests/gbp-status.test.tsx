import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { GbpCard } from '@/components/research/BusinessTab'
import type { BusinessSection } from '@/lib/api/research-types'

const business = (over: Partial<BusinessSection>): BusinessSection =>
  ({ gbp: null, socials: [], company: null, nap: {}, ...over }) as unknown as BusinessSection

describe('GbpCard when there is no profile', () => {
  afterEach(cleanup)

  it('says "no profile matched" only when Google Maps was searched', () => {
    const b = business({
      gbpStatus: 'not_found',
      gbpNote: 'Searched Google Maps for: glow med spa.',
    })
    render(<GbpCard gbp={b.gbp} business={b} />)
    expect(screen.getByText(/No Google Business Profile matched this website/)).toBeDefined()
  })

  it('says "not checked" (and no finding) when the search was not set up or failed', () => {
    const b = business({ gbpStatus: 'not_checked', gbpNote: 'The search failed (HTTP 401).' })
    render(<GbpCard gbp={b.gbp} business={b} />)
    expect(screen.getByText(/was not checked, so there is no finding/)).toBeDefined()
    expect(screen.queryByText(/No Google Business Profile matched/)).toBeNull()
  })
})
