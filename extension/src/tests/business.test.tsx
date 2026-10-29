import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildAudit } from '@/lib/api/mock/research-fixtures'
import type { BusinessSection } from '@/lib/api/research-types'

function business(over: Partial<BusinessSection> = {}): BusinessSection {
  const a = buildAudit('aud_b', 'clinic.example', 'https://clinic.example/', new Date())
  if (!a.business?.gbp) throw new Error('fixture')
  return {
    ...a.business,
    gbp: {
      ...a.business.gbp,
      matched: true,
      websiteLinksToGbp: false,
      reviewLinkOnSite: true,
    },
    nap: { ...a.business.nap, consistentWithGbp: null },
    socials: [
      { network: 'facebook', url: 'https://www.facebook.com/clinic' },
      { network: 'tiktok', url: 'https://www.tiktok.com/@clinic' },
    ],
    ...over,
  }
}

afterEach(cleanup)

describe('Business tab', () => {
  it('shows each profile signal as a result with a fix only when one is needed', async () => {
    const { ProfileSignals } = await import('@/components/research/BusinessTab')
    render(<ProfileSignals business={business()} />)
    const rows = screen.getAllByRole('listitem')
    expect(within(rows[0] as HTMLElement).getByText('Not found')).toBeTruthy()
    expect(within(rows[0] as HTMLElement).getByText(/Add one to the footer/)).toBeTruthy()
    expect(within(rows[1] as HTMLElement).getByText('Linked')).toBeTruthy()
    expect(within(rows[1] as HTMLElement).queryByText(/Add a button/)).toBeNull()
    expect(within(rows[2] as HTMLElement).getByText('Not compared')).toBeTruthy()
  })

  it('shows nothing when there is no matched profile', async () => {
    const { ProfileSignals } = await import('@/components/research/BusinessTab')
    const b = business()
    b.gbp = b.gbp ? { ...b.gbp, matched: false } : null
    const { container } = render(<ProfileSignals business={b} />)
    expect(container.textContent).toBe('')
  })

  it('copies the address and phone', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    const { GbpCard } = await import('@/components/research/BusinessTab')
    const b = business()
    if (b.gbp) b.gbp = { ...b.gbp, address: '37 SE 5th St', phone: '(561) 409-3128' }
    render(<GbpCard gbp={b.gbp} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy address' }))
    fireEvent.click(screen.getByRole('button', { name: 'Copy phone number' }))
    expect(writeText).toHaveBeenNthCalledWith(1, '37 SE 5th St')
    expect(writeText).toHaveBeenNthCalledWith(2, '(561) 409-3128')
    vi.unstubAllGlobals()
  })

  it('puts the socials and website in the card as icon links, with the match reasons', async () => {
    const { BusinessTab } = await import('@/components/research/BusinessTab')
    const b = business()
    if (b.gbp) b.gbp = { ...b.gbp, matchReasons: ['website address', 'phone number'] }
    render(<BusinessTab business={b} website="https://clinic.example" />)
    const fb = screen.getByRole('link', { name: 'Facebook (opens in a new tab)' })
    expect(fb.getAttribute('href')).toBe('https://www.facebook.com/clinic')
    expect(fb.getAttribute('target')).toBe('_blank')
    expect(screen.getByRole('link', { name: 'TikTok (opens in a new tab)' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Website (opens in a new tab)' })).toBeTruthy()
    expect(screen.getByText('Matched on website address and phone number')).toBeTruthy()
    // the separate list only appears when there is no matched profile
    expect(screen.queryByText('Socials')).toBeNull()
  })

  it('keeps the socials list when no profile was matched', async () => {
    const { BusinessTab } = await import('@/components/research/BusinessTab')
    const b = business()
    b.gbp = b.gbp ? { ...b.gbp, matched: false } : null
    render(<BusinessTab business={b} />)
    const fb = screen.getByRole('link', { name: /Facebook: facebook\.com\/clinic/ })
    expect(fb.getAttribute('href')).toBe('https://www.facebook.com/clinic')
  })

  it('shows a map picture that opens the Google listing', async () => {
    const { StaticMap } = await import('@/components/research/StaticMap')
    const { container } = render(<StaticMap href="https://maps.example/p" label="Map" />)
    expect(screen.getByRole('link', { name: 'Map' }).getAttribute('href')).toBe(
      'https://maps.example/p',
    )
    expect(container.querySelectorAll('img')).toHaveLength(1)
    expect(screen.getByText('Open in Google Maps')).toBeTruthy()
  })

  it('shows no map without a listing link', async () => {
    const { StaticMap } = await import('@/components/research/StaticMap')
    const { container } = render(<StaticMap href={null} label="Map" />)
    expect(container.textContent).toBe('')
  })
})
