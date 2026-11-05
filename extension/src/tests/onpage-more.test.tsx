import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AuditProgress } from '@/components/research/AuditProgress'
import { ImageExtras, LinkCheck, SpeedExtras } from '@/components/research/OnPageMore'
import { buildAudit } from '@/lib/api/mock/research-fixtures'
import type { OnPageSection, TraceEvent } from '@/lib/api/research-types'

afterEach(cleanup)

const base = (over: Partial<OnPageSection> = {}): OnPageSection =>
  ({
    essentials: [],
    headings: { h1Count: 1, outline: [] },
    links: { internal: 0, external: 0, nofollow: 0, items: [] },
    images: { total: 0, missingAlt: 0, lazy: 0, items: [] },
    pagespeed: null,
    ...over,
  }) as OnPageSection

const row = (url: string, status: number | null, hops = 0, foundOn: string | null = null) => ({
  url,
  status,
  hops,
  final: hops ? `${url}-new` : url,
  foundOn,
})

describe('Link and redirect check', () => {
  it('lists broken links with where they are linked from, and counts chains and redirects', () => {
    render(
      <LinkCheck
        onPage={base({
          linkCheck: {
            checked: 12,
            broken: [row('https://glow.example/gone', 404, 0, 'https://glow.example/')],
            chains: [row('https://glow.example/a', 200, 3)],
            redirects: [
              row('https://glow.example/b', 200, 1),
              row('https://glow.example/c', 200, 1),
            ],
          },
          probes: { ran: true, checked: 12, timedOut: 2, hosts: [] },
        })}
      />,
    )
    const box = screen.getByRole('region', { name: 'Link and redirect check' })
    expect(
      within(box).getByText(
        /12 links checked · 1 broken · 1 redirect chain · 2 redirects · 2 not finished/,
      ),
    ).toBeTruthy()
    expect(within(box).getByText('/gone').parentElement?.textContent).toBe('/gone · 404 · on /')
    expect(within(box).getByText('/a').parentElement?.textContent).toContain(
      '3 redirects to /a-new',
    )
  })

  it('shows where the four ways to type the address end, only for those that answered', () => {
    render(
      <LinkCheck
        onPage={base({
          probes: {
            ran: true,
            checked: 4,
            timedOut: 0,
            hosts: [
              { url: 'http://glow.example/', status: 301, final: 'https://glow.example/', hops: 1 },
              { url: 'https://www.glow.example/', status: null, final: null, hops: 0 },
            ],
          },
        })}
      />,
    )
    expect(screen.getByText('http://glow.example/')).toBeTruthy()
    expect(screen.queryByText('https://www.glow.example/')).toBeNull() // no answer: no claim
  })

  it('says the unread links were skipped, and why, for a site that blocks direct requests', () => {
    render(
      <LinkCheck onPage={base({ probes: { ran: false, checked: 0, timedOut: 0, hosts: [] } })} />,
    )
    expect(screen.getByText(/this site blocks direct requests/)).toBeTruthy()
  })

  it('lists structure problems, and shows nothing for an audit saved before these checks', () => {
    render(
      <LinkCheck
        onPage={base({
          structure: {
            deep: ['https://glow.example/services/deep'],
            noBookingLink: ['https://glow.example/services/b'],
            noRelatedLinks: [],
            maxDepth: 3,
          },
        })}
      />,
    )
    expect(screen.getByText(/Deepest page: 3 clicks/)).toBeTruthy()
    expect(screen.getByText('/services/deep')).toBeTruthy()
    expect(screen.getByText('/services/b')).toBeTruthy()
    expect(screen.queryByText('Link to no other service')).toBeNull() // empty list: no heading
    cleanup()
    const { container } = render(<LinkCheck onPage={base()} />)
    expect(container.textContent).toBe('')
  })
})

describe('Speed: real visitors and phones', () => {
  const field = {
    source: 'origin' as const,
    lcpMs: 4300,
    lcp: 'SLOW',
    inpMs: 150,
    inp: 'FAST',
    cls: 0.07,
    clsCategory: 'AVERAGE',
  }

  it('shows each real-visitor number with Google’s verdict and where it was measured', () => {
    render(
      <SpeedExtras
        p={{ ...base().pagespeed, field, tapTargetsOk: true, zoomOk: false } as never}
      />,
    )
    const real = screen.getByRole('region', { name: 'Real visitors' })
    expect(within(real).getByText(/for the whole site/)).toBeTruthy()
    expect(within(real).getByText('Main content shows').parentElement?.textContent).toContain(
      '4.3 sPoor',
    )
    expect(within(real).getByText('Reacts to a tap').parentElement?.textContent).toContain(
      '150 msGood',
    )
    expect(within(real).getByText('Page stays still').parentElement?.textContent).toContain(
      '0.07Needs work',
    )
    const phones = screen.getByRole('region', { name: 'On phones' })
    expect(
      within(phones).getByText('Buttons and links are easy to tap').parentElement?.textContent,
    ).toContain('Fine')
    expect(within(phones).getByText('Visitors can zoom in').parentElement?.textContent).toContain(
      'Zoom is blocked',
    )
  })

  it('explains a missing real-visitor number instead of showing an empty block', () => {
    render(<SpeedExtras p={{ field: null } as never} />)
    expect(screen.getByText(/No real-visitor data/)).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'On phones' })).toBeNull() // not measured: not shown
  })

  it('shows nothing for an audit saved before these were measured', () => {
    const { container } = render(<SpeedExtras p={{ mobilePerformance: 70 } as never} />)
    expect(container.textContent).toBe('')
    cleanup()
    expect(render(<SpeedExtras p={null} />).container.textContent).toBe('')
  })
})

describe('Picture size and placement', () => {
  it('reports unsized images, CSS backgrounds and large files', () => {
    const im = {
      ...base().images,
      noDimensions: 5,
      cssBackgrounds: 1,
      sizesChecked: 6,
      large: [{ url: 'https://glow.example/wp/hero.jpg', bytes: 912_000 }],
    }
    render(<ImageExtras im={im} />)
    expect(screen.getByText('5 images have no width and height.')).toBeTruthy()
    expect(screen.getByText('1 picture is set as CSS backgrounds.')).toBeTruthy()
    expect(screen.getByText('6 home page images measured; 1 over 400 KB.')).toBeTruthy()
    expect(screen.getByText('/wp/hero.jpg · 912 KB')).toBeTruthy()
  })

  it('shows nothing when none of it was measured', () => {
    expect(render(<ImageExtras im={base().images} />).container.textContent).toBe('')
  })
})

describe('Audit log: the link step', () => {
  const ev = (over: Partial<TraceEvent>): TraceEvent => ({
    id: 'probe',
    status: 'done',
    label: 'Check links and redirects',
    ms: 4100,
    at: '2026-11-04T10:00:00Z',
    detail: { checked: 31, timedOut: 2 },
    ...over,
  })

  it('shows how many requests were made and how many ran out of time', () => {
    const audit = {
      ...buildAudit('a', 'glow.example', 'https://glow.example/', new Date()),
      status: 'running' as const,
      finishedAt: null,
      trace: [ev({})],
    }
    render(<AuditProgress audit={audit} />)
    expect(screen.getByText('Check links and redirects')).toBeTruthy()
    expect(screen.getByText('31 requests made, 2 not finished in time')).toBeTruthy()
  })

  it('shows the reason when the step was skipped', () => {
    const audit = {
      ...buildAudit('a', 'glow.example', 'https://glow.example/', new Date()),
      status: 'running' as const,
      finishedAt: null,
      trace: [
        ev({ status: 'skipped', detail: { reason: 'The site blocks direct requests' }, ms: null }),
      ],
    }
    render(<AuditProgress audit={audit} />)
    expect(screen.getByText('The site blocks direct requests')).toBeTruthy()
  })
})
