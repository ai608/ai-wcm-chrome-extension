import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AuditProgress } from '@/components/research/AuditProgress'
import { buildAudit, mockTrace } from '@/lib/api/mock/research-fixtures'
import type { Audit, TraceEvent } from '@/lib/api/research-types'

afterEach(cleanup)

const started = new Date('2026-11-04T10:00:00Z')

function finished(mutate?: (usage: TraceEvent) => void, drop?: string): Audit {
  const trace = mockTrace('glowmedspa.com', 7000, false, started).filter((e) => e.id !== drop)
  const usage = trace.find((e) => e.id === 'usage')
  if (usage) mutate?.(usage)
  return { ...buildAudit('aud_u', 'glowmedspa.com', 'https://glowmedspa.com/', started), trace }
}

const open = () => fireEvent.click(screen.getByText('How this audit ran'))
const rows = () =>
  [...document.querySelectorAll('ol.divide-y > li')].map((li) => li.textContent ?? '')

describe('main audit: cost and tokens', () => {
  it('shows total cost, total tokens, the input/output split and the run time', () => {
    render(<AuditProgress audit={finished()} />)
    open()
    expect(screen.getByText('Cost and tokens')).toBeTruthy()
    expect(screen.getAllByText('$0.1226')[0]?.parentElement?.textContent).toContain(
      '117,888 tokens',
    )
    expect(
      screen.getByText(/111,291 input · 6,597 output · 1 AI call · 6\.0 s in all/),
    ).toBeTruthy()
  })

  it('the cost step sits right before the last step', () => {
    render(<AuditProgress audit={finished()} />)
    open()
    const texts = rows()
    const cost = texts.findIndex((t) => t.includes('Cost and tokens'))
    expect(cost).toBeGreaterThan(-1)
    expect(texts[cost + 1]).toContain('Audit finished')
    expect(cost + 2).toBe(texts.length)
  })

  it('Firecrawl and Apify show as call counts, never as dollars', () => {
    render(<AuditProgress audit={finished()} />)
    open()
    expect(screen.getByText('Firecrawl 11 calls · Google Maps (Apify) 1 call')).toBeTruthy()
    fireEvent.click(screen.getByText('Show breakdown'))
    const fc = screen.getByText('Firecrawl').closest('tr')
    expect(fc?.textContent).toContain('1 map, 10 scrapes')
    expect(fc?.textContent).toContain('11 calls')
    expect(fc?.textContent).toContain('credits')
    expect(fc?.textContent).not.toContain('$')
    expect(screen.getByText(/dollar total counts AI calls only/)).toBeTruthy()
    const ai = screen.getByText(/Page analysis · claude-sonnet-5\.5/).closest('tr')
    expect(ai?.textContent).toContain('117,888')
    expect(ai?.textContent).toContain('$0.1226')
  })

  it('an audit with no AI call says so and still lists provider calls', () => {
    const a = finished((u) => {
      u.detail = {
        calls: 0,
        tokens: 0,
        costUsd: 0,
        lines: [{ kind: 'firecrawl', label: 'Firecrawl', calls: 3, note: '3 scrapes' }],
      }
    })
    render(<AuditProgress audit={a} />)
    open()
    expect(screen.getByText(/No AI calls/)).toBeTruthy()
    expect(screen.getByText('Firecrawl 3 calls')).toBeTruthy()
    expect(screen.queryByText('$0')).toBeNull()
  })

  it('a tiny cost never shows as $0.0000', () => {
    const a = finished((u) => {
      u.detail = { ...u.detail, costUsd: 0.00004 }
    })
    render(<AuditProgress audit={a} />)
    open()
    expect(screen.getByText('<$0.0001')).toBeTruthy()
  })

  it('an older audit without the step shows no cost row, and a running audit shows no waiting row', () => {
    render(<AuditProgress audit={finished(undefined, 'usage')} />)
    open()
    expect(screen.queryByText('Cost and tokens')).toBeNull()
    cleanup()
    const running: Audit = {
      ...buildAudit('aud_r', 'glowmedspa.com', 'https://glowmedspa.com/', started),
      status: 'running',
      finishedAt: null,
      trace: mockTrace('glowmedspa.com', 2600, false, started),
    }
    render(<AuditProgress audit={running} />)
    expect(screen.queryByText('Cost and tokens')).toBeNull()
  })
})
