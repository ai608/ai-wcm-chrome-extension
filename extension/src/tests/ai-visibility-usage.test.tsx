import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { aiVisibilityFixture, buildAudit } from '@/lib/api/mock/research-fixtures'
import type { AiVisibility, Audit } from '@/lib/api/research-types'

vi.mock('@/lib/messaging', () => ({ call: async () => null }))

const PROMPTS = ['best med spa in Austin', 'top rated botox near Austin']

function auditWith(data: AiVisibility): Audit {
  const a = buildAudit('aud_use', 'glow.com', 'https://glow.com/', new Date())
  if (!a.research) throw new Error('fixture has no research section')
  a.research.aiVisibility = { state: 'ready', data, error: null, ranAt: null }
  return a
}

async function show(data: AiVisibility) {
  const { Providers } = await import('@/app/providers')
  const { AiVisibilityPanel } = await import('@/components/research/AiVisibilityPanel')
  render(
    <Providers>
      <AiVisibilityPanel audit={auditWith(data)} initialPrompts={PROMPTS} />
    </Providers>,
  )
  fireEvent.click(screen.getByText('How this check ran'))
}

const usageStep = (data: AiVisibility) => {
  const e = data.log.find((x) => x.id === 'usage')
  if (!e) throw new Error('fixture has no usage step')
  return e
}

beforeEach(async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  fakeBrowser.reset()
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('AI visibility cost and tokens', () => {
  it('shows total cost, total tokens and the input/output split in the run log', async () => {
    await show(aiVisibilityFixture(true, PROMPTS))
    expect(screen.getByText('Cost and tokens')).toBeTruthy()
    expect(screen.getByText('$0.0123').parentElement?.textContent).toContain('4,800 tokens')
    expect(screen.getByText(/4,000 input · 800 output/)).toBeTruthy()
    expect(screen.getByText(/800 output · 8 answers/)).toBeTruthy()
  })

  it('the cost step sits right before the last step', async () => {
    await show(aiVisibilityFixture(true, PROMPTS))
    const rows = screen.getByLabelText('AI visibility steps').querySelectorAll(':scope > li')
    const texts = [...rows].map((li) => li.textContent ?? '')
    const cost = texts.findIndex((t) => t.includes('Cost and tokens'))
    expect(cost).toBeGreaterThan(-1)
    expect(texts[cost + 1]).toContain('AI visibility check')
    expect(cost + 2).toBe(texts.length)
  })

  it('the breakdown lists every engine with its tokens and cost', async () => {
    await show(aiVisibilityFixture(true, PROMPTS))
    fireEvent.click(screen.getByText('Show breakdown'))
    for (const engine of ['ChatGPT', 'Gemini', 'Perplexity', 'Claude']) {
      const row = screen
        .getAllByText(engine)
        .map((el) => el.closest('tr'))
        .find((tr) => tr !== null)
      expect(row, `no breakdown row for ${engine}`).toBeTruthy()
      expect(row?.textContent).toContain('1,200')
    }
    expect(screen.getByText('$0.0050')).toBeTruthy()
  })

  it('the competitor-check (judge) call is its own row when it ran', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    usageStep(data).detail.judge = { tokens: 500, costUsd: 0.0009 }
    await show(data)
    fireEvent.click(screen.getByText('Show breakdown'))
    expect(screen.getByText('Competitor check (AI)').parentElement?.textContent).toContain(
      '$0.0009',
    )
  })

  it('failed answers are counted out and a tiny cost never shows as $0.0000', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    Object.assign(usageStep(data).detail, { failed: 2, costUsd: 0.00004 })
    await show(data)
    expect(screen.getByText('<$0.0001')).toBeTruthy()
    expect(screen.getByText(/6 answers \(2 failed\)/)).toBeTruthy()
  })

  it('an older saved check without the cost step still shows its totals once', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    data.log = data.log.filter((e) => e.id !== 'usage')
    await show(data)
    expect(screen.queryByText('Cost and tokens')).toBeNull()
    expect(screen.getAllByText(/4800 tokens/).length).toBe(1)
  })
})
