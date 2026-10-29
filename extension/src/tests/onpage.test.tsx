import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { buildAudit } from '@/lib/api/mock/research-fixtures'
import type { Audit, OnPageSection } from '@/lib/api/research-types'

type Link = OnPageSection['links']['items'][number]

const internal = (path: string, text: string): Link => ({
  href: `https://clinic.example${path}`,
  text,
  kind: 'internal',
  nofollow: false,
})

// Real menus repeat links (header + footer), which gives identical href/text pairs.
const LINKS: Link[] = [
  internal('/', 'Home'),
  internal('/meet-the-team/', 'Meet the Team'),
  internal('/', 'Home'),
  internal('/services/', 'Services'),
  internal('/', 'Home'),
  { href: 'https://instagram.com/clinic', text: 'Instagram', kind: 'external', nofollow: false },
  { href: 'https://g.page/clinic', text: 'Reviews', kind: 'external', nofollow: true },
]

function auditWith(onPage: Partial<OnPageSection>): Audit {
  const a = buildAudit('aud_t', 'clinic.example', 'https://clinic.example/', new Date())
  if (!a.onPage) throw new Error('fixture')
  a.onPage = { ...a.onPage, ...onPage }
  return a
}

async function open(sub: 'Links' | 'Speed' | 'Headings' | 'Images', audit: Audit) {
  const { OnPageTab } = await import('@/components/research/OnPageTab')
  if (!audit.onPage) throw new Error('fixture')
  render(<OnPageTab audit={audit} onPage={audit.onPage} />)
  fireEvent.click(screen.getByRole('button', { name: sub }))
}

const rows = () => within(screen.getByRole('list', { name: 'Links' })).queryAllByRole('listitem')

beforeEach(async () => {
  const { usePanelStore } = await import('@/stores/panel-store')
  usePanelStore.setState({ researchSubTab: {} })
})
afterEach(cleanup)

describe('On-Page links', () => {
  const audit = () => auditWith({ links: { internal: 5, external: 2, nofollow: 1, items: LINKS } })

  it('filters by kind, and switching back restores the list', async () => {
    await open('Links', audit())
    expect(rows()).toHaveLength(5) // Home ×3 folds into one row
    fireEvent.click(screen.getByRole('button', { name: /^External/ }))
    expect(rows().map((r) => r.textContent)).toEqual([
      expect.stringContaining('Instagram'),
      expect.stringContaining('Reviews'),
    ])
    fireEvent.click(screen.getByRole('button', { name: /^Nofollow/ }))
    expect(rows()).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /^Internal/ }))
    expect(rows()).toHaveLength(3)
    expect(screen.queryByText('Instagram')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^All/ }))
    expect(rows()).toHaveLength(5)
  })

  it('folds repeated links and shows how often they appear', async () => {
    await open('Links', audit())
    const home = rows().find((r) => r.textContent?.includes('Home'))
    expect(home?.textContent).toContain('×3')
  })

  it('searches link text and URL', async () => {
    await open('Links', audit())
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search links' }), {
      target: { value: 'team' },
    })
    expect(rows()).toHaveLength(1)
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search links' }), {
      target: { value: 'nothing-matches' },
    })
    expect(screen.getByText('No links match.')).toBeDefined()
  })

  it('renders the first 50 and shows the rest on request', async () => {
    const many = Array.from({ length: 70 }, (_, i) => internal(`/p${i}/`, `Page ${i}`))
    await open(
      'Links',
      auditWith({ links: { internal: 70, external: 0, nofollow: 0, items: many } }),
    )
    expect(rows()).toHaveLength(50)
    fireEvent.click(screen.getByRole('button', { name: 'Show all 70' }))
    expect(rows()).toHaveLength(70)
  })
})

describe('On-Page speed', () => {
  it('bands scores and vitals the way PageSpeed does', async () => {
    const { scoreBand, lcpBand, clsBand } = await import('@/components/research/OnPageTab')
    expect([scoreBand(49), scoreBand(50), scoreBand(89), scoreBand(90)]).toEqual([
      'poor',
      'average',
      'average',
      'good',
    ])
    expect([lcpBand(2500), lcpBand(2501), lcpBand(4000), lcpBand(4001)]).toEqual([
      'good',
      'average',
      'average',
      'poor',
    ])
    expect([clsBand(0.1), clsBand(0.11), clsBand(0.25), clsBand(0.26)]).toEqual([
      'good',
      'average',
      'average',
      'poor',
    ])
  })

  it('shows scores and plain-language vitals, and handles missing values', async () => {
    await open(
      'Speed',
      auditWith({
        pagespeed: {
          mobilePerformance: 96,
          seo: 100,
          accessibility: 42,
          bestPractices: null,
          lcpMs: 2000,
          cls: 0.009,
        },
      }),
    )
    expect(screen.getByLabelText('Performance 96, good')).toBeDefined()
    expect(screen.getByLabelText('Accessibility 42, poor')).toBeDefined()
    expect(screen.getByLabelText('Best practices not measured')).toBeDefined()
    expect(screen.getByText('Main content shows in 2.0 s.')).toBeDefined()
    expect(screen.getByText('The page barely moves while it loads.')).toBeDefined()
  })

  const both = {
    mobilePerformance: 40,
    seo: 90,
    accessibility: 80,
    bestPractices: 70,
    lcpMs: 5000,
    cls: 0.3,
    desktop: {
      performance: 95,
      seo: 91,
      accessibility: 81,
      bestPractices: 71,
      lcpMs: 1200,
      cls: 0.02,
    },
  }
  const report = () =>
    screen.getByRole('link', { name: /Open full report/ }).getAttribute('href') ?? ''

  it('defaults to Mobile and switches to the desktop numbers', async () => {
    await open('Speed', auditWith({ pagespeed: both }))
    const mobile = screen.getByRole('button', { name: 'Mobile' })
    const desktop = screen.getByRole('button', { name: 'Desktop' })
    expect(mobile.getAttribute('aria-pressed')).toBe('true')
    expect(desktop.getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByLabelText('Performance 40, poor')).toBeDefined()
    expect(screen.getByText('Main content shows in 5.0 s.')).toBeDefined()
    expect(report()).toContain('&form_factor=mobile')
    fireEvent.click(desktop)
    expect(desktop.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByLabelText('Performance 95, good')).toBeDefined()
    expect(screen.getByText('Main content shows in 1.2 s.')).toBeDefined()
    expect(report()).toBe(
      'https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fclinic.example%2F&form_factor=desktop',
    )
    fireEvent.click(mobile)
    expect(screen.getByLabelText('Performance 40, poor')).toBeDefined()
  })

  it.each([{ desktop: undefined }, { desktop: null }])(
    'says desktop was not measured when it is missing ($desktop)',
    async ({ desktop }) => {
      await open('Speed', auditWith({ pagespeed: { ...both, desktop } }))
      fireEvent.click(screen.getByRole('button', { name: 'Desktop' }))
      expect(
        screen.getByText('Desktop wasn’t measured for this audit. Re-run the audit to get it.'),
      ).toBeDefined()
      expect(screen.queryByLabelText(/^Performance/)).toBeNull()
      expect(report()).toContain('&form_factor=desktop')
    },
  )

  it('explains when there is no PageSpeed data', async () => {
    await open('Speed', auditWith({ pagespeed: null }))
    expect(screen.getByText('No PageSpeed data for this audit.')).toBeDefined()
    expect(screen.getByRole('link', { name: /Run it on PageSpeed/ })).toBeDefined()
  })
})

describe('imageName', () => {
  it('names embedded images instead of printing the file', async () => {
    const { imageName } = await import('@/components/research/OnPageTab')
    expect(imageName(`data:image/png;base64,${'A'.repeat(5000)}`)).toBe('Embedded PNG image')
    expect(imageName('data:image/svg+xml,')).toBe('Embedded SVG image')
    expect(imageName('https://clinic.example/img/hero%20shot.webp?v=2')).toBe('hero shot.webp')
  })
})

describe('On-Page headings', () => {
  const outline: OnPageSection['headings']['outline'] = [
    { level: 1, text: 'Glow Med Spa' },
    { level: 2, text: 'Services' },
    { level: 4, text: 'Botox' },
    { level: 2, text: '' },
  ]

  it('counts levels and marks headings that skip a level', async () => {
    const { skippedLevels } = await import('@/components/research/OnPageTab')
    expect([...skippedLevels(outline)]).toEqual([2])
    await open('Headings', auditWith({ headings: { h1Count: 1, outline } }))
    expect(screen.getByText('Exactly one H1')).toBeTruthy()
    expect(screen.getByText('1 heading skips a level')).toBeTruthy()
    expect(screen.getByText(/4 headings · 1 H1 · 2 H2 · 1 H4/)).toBeTruthy()
    expect(screen.getAllByText('Skips a level')).toHaveLength(1)
    expect(screen.getByText('Empty heading')).toBeTruthy()
  })

  it('shows an empty state and disables copy when there are no headings', async () => {
    await open('Headings', auditWith({ headings: { h1Count: 0, outline: [] } }))
    expect(screen.getByText('No H1 on this page')).toBeTruthy()
    expect(screen.getByText('This page has no headings.')).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: /Copy outline/ }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})

describe('Row alignment', () => {
  it('keeps the dot slot on rows without a status', async () => {
    const { Row } = await import('@/components/research/shared')
    const { container } = render(
      <>
        <Row label="Posts">12</Row>
        <Row label="Last post" status="ok">
          today
        </Row>
      </>,
    )
    const [plain, dotted] = Array.from(container.children)
    expect(plain?.children).toHaveLength(dotted?.children.length ?? -1)
    expect(plain?.firstElementChild?.classList.contains('size-2')).toBe(true)
  })
})

describe('On-Page images', () => {
  const items = [
    { src: 'https://clinic.example/a.jpg', alt: 'Team', width: 400, height: 300 },
    { src: 'https://clinic.example/px.gif', alt: null, width: 1, height: 1 },
    { src: 'data:image/png;base64,', alt: null, width: null, height: null },
  ]

  it('previews real images, skips tracking pixels, and filters by missing alt', async () => {
    await open('Images', auditWith({ images: { total: 3, missingAlt: 2, lazy: 0, items } }))
    const list = screen.getByRole('list', { name: 'Images' })
    // only the real image is fetched; the pixel and the embedded image get a placeholder
    expect(list.querySelectorAll('img')).toHaveLength(1)
    expect(within(list).getByText('Tracking pixel')).toBeTruthy()
    expect(within(list).getByText('Embedded PNG image')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /^Missing alt 2/ }))
    expect(
      within(screen.getByRole('list', { name: 'Images' })).getAllByRole('listitem'),
    ).toHaveLength(2)
  })

  it('caps long lists until asked', async () => {
    const many = Array.from({ length: 60 }, (_, n) => ({
      src: `https://clinic.example/${n}.jpg`,
      alt: `Image ${n}`,
      width: 10,
      height: 10,
    }))
    await open('Images', auditWith({ images: { total: 60, missingAlt: 0, lazy: 0, items: many } }))
    expect(
      within(screen.getByRole('list', { name: 'Images' })).getAllByRole('listitem'),
    ).toHaveLength(50)
    fireEvent.click(screen.getByRole('button', { name: 'Show all 60' }))
    expect(
      within(screen.getByRole('list', { name: 'Images' })).getAllByRole('listitem'),
    ).toHaveLength(60)
  })
})

describe('Site → Blog', () => {
  const blog = (over: Record<string, unknown>) => {
    const a = buildAudit('aud_b', 'clinic.example', 'https://clinic.example/', new Date())
    if (!a.site) throw new Error('fixture')
    a.site = { ...a.site, blog: { ...a.site.blog, ...over } }
    return a
  }
  const show = async (a: Audit) => {
    const { SiteTab } = await import('@/components/research/SiteTab')
    const { usePanelStore } = await import('@/stores/panel-store')
    usePanelStore.setState({ researchSubTab: { site: 'blog' } })
    if (!a.site) throw new Error('fixture')
    render(<SiteTab audit={a} site={a.site} />)
  }

  it('says the counts are minimums when most posts have no date', async () => {
    await show(
      blog({
        postCount: 80,
        datedPosts: 2,
        postsLast6Months: 1,
        postsLast12Months: 1,
        lastPostAt: '2025-07-11T00:00:00Z',
      }),
    )
    expect(
      screen.getByText(/At least 1 in the last 6 months, 1 in the last 12 months/),
    ).toBeTruthy()
    expect(screen.getByText('Dates found for 2 of 80 posts.')).toBeTruthy()
  })

  it('shows plain counts when every post is dated, and "Date not found" without any', async () => {
    await show(
      blog({
        postCount: 20,
        datedPosts: 20,
        postsLast6Months: 17,
        postsLast12Months: 19,
        lastPostAt: new Date().toISOString(),
      }),
    )
    expect(screen.getByText(/17 in the last 6 months, 19 in the last 12 months/)).toBeTruthy()
    expect(screen.queryByText(/At least/)).toBeNull()
    cleanup()
    await show(
      blog({
        postCount: 5,
        datedPosts: 0,
        postsLast6Months: 0,
        postsLast12Months: 0,
        lastPostAt: null,
      }),
    )
    expect(screen.getByText('Date not found')).toBeTruthy()
  })
})
