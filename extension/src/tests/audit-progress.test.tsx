import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AuditProgress, foldTrace } from '@/components/research/AuditProgress'
import { buildAudit, mockTrace } from '@/lib/api/mock/research-fixtures'
import type { Audit, TraceEvent } from '@/lib/api/research-types'

afterEach(cleanup)

const started = new Date('2026-10-21T10:00:00Z')

const audit = (over: Partial<Audit>, trace: TraceEvent[]): Audit => ({
  ...buildAudit('aud_t', 'glowmedspa.com', 'https://glowmedspa.com/', started),
  trace,
  ...over,
})

describe('foldTrace', () => {
  it('keeps the last event per id in first-seen order', () => {
    const t = mockTrace('glowmedspa.com', 1000, false, started)
    const folded = foldTrace([
      ...t,
      { id: 'home', status: 'failed', label: 'Fetch home page', ms: 9, at: 'x', detail: {} },
    ])
    expect([...folded.keys()].slice(0, 2)).toEqual(['home', 'analyze'])
    expect(folded.get('home')?.status).toBe('failed')
  })
})

describe('AuditProgress', () => {
  it('shows finished steps, a spinner and waiting steps while running', () => {
    const a = audit(
      { status: 'running', finishedAt: null },
      mockTrace('glowmedspa.com', 2600, false, started),
    )
    render(<AuditProgress audit={a} />)
    const box = screen.getByRole('region', { name: 'Audit progress' })
    expect(within(box).getByText('Audit progress')).toBeTruthy()
    expect(within(box).getByText('142 URLs found')).toBeTruthy()
    expect(within(box).getByText('9 pages chosen')).toBeTruthy()
    expect(within(box).getByText('4/9 pages read')).toBeTruthy()
    expect(within(box).getAllByLabelText('running').length).toBeGreaterThan(0)
    expect(within(box).getAllByLabelText('waiting').length).toBeGreaterThan(0)
  })

  it('shows a collapsed "How this audit ran" with page results once finished', () => {
    const a = audit({}, mockTrace('glowmedspa.com', 7000, false, started))
    const { container } = render(<AuditProgress audit={a} />)
    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(screen.getByText('How this audit ran')).toBeTruthy()
    expect(screen.getByText('8 read, 1 failed')).toBeTruthy()
    expect(screen.getByText('Audit finished')).toBeTruthy()
    const chosen = screen.getByText('Show chosen pages').closest('details')
    expect(chosen?.className).toContain('group/pages')
    expect(chosen?.querySelector('svg')?.getAttribute('class')).toContain(
      'group-open/pages:rotate-90',
    )
    expect(screen.queryByText('Audit progress')).toBeNull()
  })

  it('collapses when the tab changes', () => {
    const a = audit({}, mockTrace('glowmedspa.com', 7000, false, started))
    const { rerender, container } = render(<AuditProgress audit={a} tab="overview" />)
    fireEvent.click(screen.getByText('How this audit ran'))
    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(true)
    rerender(<AuditProgress audit={a} tab="business" />)
    expect(details.open).toBe(false)
  })

  it('hides the finished trace on the Research tab', () => {
    const a = audit({}, mockTrace('glowmedspa.com', 7000, false, started))
    render(<AuditProgress audit={a} tab="research" />)
    expect(screen.queryByText('How this audit ran')).toBeNull()
  })

  it('opens by default and marks the failed step when the audit failed', () => {
    const a = audit({ status: 'failed', error: 'Website could not be fetched' }, [
      {
        id: 'home',
        status: 'failed',
        label: 'Fetch home page',
        ms: 120,
        at: 'a',
        detail: { error: 'Website could not be fetched' },
      },
      {
        id: 'final',
        status: 'failed',
        label: 'Audit finished',
        ms: null,
        at: 'b',
        detail: { outcome: 'failed' },
      },
    ])
    const { container } = render(<AuditProgress audit={a} />)
    expect((container.querySelector('details') as HTMLDetailsElement).open).toBe(true)
    expect(screen.getAllByLabelText('failed').length).toBe(2)
    expect(screen.getByText('Website could not be fetched')).toBeTruthy()
    expect(screen.getByText('Audit failed')).toBeTruthy()
  })

  it('keeps read pages in a five-row queue with no scrollbar', () => {
    const pages: TraceEvent[] = Array.from({ length: 7 }, (_, i) => ({
      id: `page:https://glowmedspa.com/p${i}`,
      status: 'done',
      label: `/p${i}`,
      ms: 1000 + i,
      at: `t${i}`,
      detail: { url: `https://glowmedspa.com/p${i}` },
    }))
    render(
      <AuditProgress
        audit={audit({ status: 'running', finishedAt: null }, [
          { id: 'scrape', status: 'running', label: 'Read pages', ms: null, at: 's', detail: {} },
          ...pages,
        ])}
      />,
    )
    const queue = document.querySelector('[data-page-queue]')
    expect(queue?.getAttribute('data-page-queue')).toBe('5')
    expect(queue?.className).toContain('overflow-hidden')
    expect(queue?.className).not.toContain('overflow-y-auto')
    expect(screen.queryByText('Show all pages')).toBeNull()
    expect(screen.getByText('/p0').closest('li')?.getAttribute('aria-hidden')).toBe('true')
    expect(screen.getByText('/p1').closest('li')?.getAttribute('aria-hidden')).toBe('true')
    expect(screen.getByText('/p2').closest('li')?.hasAttribute('aria-hidden')).toBe(false)
    expect(screen.getByText('/p6').closest('li')?.hasAttribute('aria-hidden')).toBe(false)
  })

  it('shows why a step was skipped and renders nothing for an old audit without a trace', () => {
    const a = audit({}, [
      {
        id: 'psi',
        status: 'skipped',
        label: 'PageSpeed',
        ms: null,
        at: 'a',
        detail: { reason: 'PageSpeed key not set' },
      },
    ])
    const { rerender, container } = render(<AuditProgress audit={a} />)
    expect(screen.getByText('PageSpeed key not set')).toBeTruthy()
    rerender(<AuditProgress audit={audit({}, [])} />)
    expect(container.innerHTML).toBe('')
  })
})

describe('PageSpeed summary line', () => {
  const psi = (detail: TraceEvent['detail']): Audit =>
    audit({ status: 'ready' }, [
      { id: 'psi', status: 'done', label: 'PageSpeed', ms: 1200, at: 'x', detail },
    ])

  it('shows mobile and desktop for new audits, and mobile only for older ones', () => {
    const { rerender } = render(<AuditProgress audit={psi({ mobile: 71, desktop: 94 })} />)
    expect(screen.getByText('Performance: mobile 71, desktop 94')).toBeTruthy()
    rerender(<AuditProgress audit={psi({ mobile: 71, desktop: null })} />)
    expect(screen.getByText('Mobile performance 71')).toBeTruthy()
    rerender(<AuditProgress audit={psi({ performance: 64 })} />)
    expect(screen.getByText('Mobile performance 64')).toBeTruthy()
  })
})
