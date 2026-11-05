import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { aiVisibilityFixture, buildAudit } from '@/lib/api/mock/research-fixtures'
import type { AiVisibility, Audit, OnDemand } from '@/lib/api/research-types'

const calls: { key: string; data: Record<string, unknown> }[] = []
vi.mock('@/lib/messaging', () => ({
  call: async (key: string, data: Record<string, unknown> = {}) => {
    calls.push({ key, data })
    return null
  },
}))

const PROMPTS = ['best med spa in Austin', 'top rated botox near Austin']

function auditWith(od: OnDemand<AiVisibility>): Audit {
  const a = buildAudit('aud_ai', 'glow.com', 'https://glow.com/', new Date())
  if (!a.research) throw new Error('fixture has no research section')
  a.research.aiVisibility = od
  return a
}

const od = (
  state: OnDemand<AiVisibility>['state'],
  data: AiVisibility | null,
  error: string | null = null,
): OnDemand<AiVisibility> => ({ state, data, error, ranAt: null })

async function show(audit: Audit) {
  const { Providers } = await import('@/app/providers')
  const { AiVisibilityPanel } = await import('@/components/research/AiVisibilityPanel')
  return render(
    <Providers>
      <AiVisibilityPanel audit={audit} initialPrompts={[...PROMPTS, 'near me']} />
    </Providers>,
  )
}

beforeEach(async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'false')
  fakeBrowser.reset()
  calls.length = 0
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
  const { usePanelStore } = await import('@/stores/panel-store')
  usePanelStore.setState({ researchSubTab: {} })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('AI visibility panel', () => {
  it('not run: sends at most three trimmed, non-empty questions', async () => {
    await show(auditWith(od('not_run', null)))
    fireEvent.change(screen.getByLabelText('Question 1'), { target: { value: '  best spa  ' } })
    fireEvent.change(screen.getByLabelText('Question 2'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check AI visibility' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]?.key).toBe('runAiVisibility')
    // trimming is the backend's job; empty slots must not be sent
    expect(calls[0]?.data.prompts).toEqual(['  best spa  ', 'near me'])
  })

  it('running: shows the live step log and how many answers are in', async () => {
    const live = aiVisibilityFixture(true, PROMPTS)
    live.engines = []
    live.log = [
      ...live.log.slice(0, 2),
      { ...live.log[2], id: 'ask:ChatGPT:1', status: 'done', ms: 1800 },
      { ...live.log[3], status: 'running', ms: null },
      { ...live.log[4], status: 'failed', ms: 900, detail: { error: 'HTTP 429' } },
    ] as AiVisibility['log']
    await show(auditWith(od('running', live)))
    expect(screen.getByRole('status').textContent).toContain('2 of 3 answers')
    expect(screen.getByText('ChatGPT')).toBeTruthy()
    const questions = screen.getAllByRole('button', { name: 'Show questions' })
    expect(questions.every((button) => button.getAttribute('aria-expanded') === 'false')).toBe(true)
    fireEvent.click(questions[0]!)
    expect(screen.getByText('top rated botox near Austin')).toBeTruthy()
    expect(screen.queryByText('ChatGPT · question 1')).toBeNull()
    expect(screen.getAllByLabelText('running').length).toBeGreaterThan(0)
    expect(screen.getByText('HTTP 429')).toBeTruthy()
  })

  it('shows the longest of the three question times, not their sum', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    const kept = data.log.filter((event) => !event.id.startsWith('ask:'))
    data.log = [
      ...kept,
      {
        id: 'ask:ChatGPT:0',
        status: 'done',
        label: 'ChatGPT · question 1',
        ms: 10000,
        at: 'a',
        detail: {},
      },
      {
        id: 'ask:ChatGPT:1',
        status: 'done',
        label: 'ChatGPT · question 2',
        ms: 66400,
        at: 'a',
        detail: {},
      },
      {
        id: 'ask:ChatGPT:2',
        status: 'done',
        label: 'ChatGPT · question 3',
        ms: 20000,
        at: 'a',
        detail: {},
      },
    ]
    await show(auditWith(od('ready', data)))
    fireEvent.click(screen.getByRole('button', { name: 'How this check ran' }))
    expect(screen.getAllByText('66.4 s').length).toBeGreaterThan(0)
    expect(screen.queryByText('96.4 s')).toBeNull()
  })

  it('keeps the preview short and opens the full answer', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    const answer = data.engines[0]?.answers[0]
    if (!answer) throw new Error('fixture has no answer')
    answer.excerpt = 'Glow Aesthetics is recommended…'
    answer.text = 'Glow Aesthetics is recommended for Botox and also offers evening visits.'
    await show(auditWith(od('ready', data)))
    fireEvent.click(screen.getAllByRole('button', { name: 'Answers' })[0]!)
    expect(screen.queryByText(/evening visits/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'See full answer' }))
    expect(screen.getByText(/evening visits/)).toBeTruthy()
  })

  it('ready: plain summary, per-engine result, source note, cost line and a log', async () => {
    await show(auditWith(od('ready', aiVisibilityFixture(true, PROMPTS))))
    expect(screen.getByText(/was named in 4 of 8 answers/)).toBeTruthy()
    const marks = screen
      .getAllByText('ChatGPT')
      .map((node) => node.parentElement?.querySelector('img')?.getAttribute('src') ?? '')
    expect(marks.length).toBeGreaterThan(0)
    expect(marks.every((src) => src.length > 0)).toBe(true)
    const card = screen
      .getAllByText('ChatGPT')
      .map((node) => node.closest('li'))
      .find((item) => item?.className.includes('rounded-md'))
    expect(card?.className).toContain('bg-foreground')
    expect(screen.getAllByText('✓ Named')).toHaveLength(2)
    expect(screen.getAllByText('✗ Not named')).toHaveLength(2)
    expect(screen.getAllByText('Linked')).toHaveLength(1)
    expect(screen.getByText(/Compared with 3 local competitors from Google Maps/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'How this check ran' }))
    expect(screen.getByText('Cost and tokens')).toBeTruthy()
    expect(screen.getByText(/\$0\.0123/)).toBeTruthy()
  })

  it('ready without a Google Maps list: says so and sends the SDR to Local Competitors', async () => {
    const data = aiVisibilityFixture(false, PROMPTS)
    data.competitors = { source: 'none', names: [] }
    await show(auditWith(od('ready', data)))
    expect(screen.getByText(/No competitors were compared/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Find competitors' }))
    const { usePanelStore } = await import('@/stores/panel-store')
    expect(usePanelStore.getState().researchSubTab.research).toBe('local')
  })

  it('a failed engine is shown as did not answer, not as not named', async () => {
    const data = aiVisibilityFixture(true, PROMPTS)
    const bad = data.engines[3]
    if (!bad) throw new Error('fixture has no fourth engine')
    Object.assign(bad, { promptsFailed: 2, error: 'HTTP 500', cited: false, mentioned: false })
    await show(auditWith(od('ready', data)))
    expect(screen.getByText('Did not answer')).toBeTruthy()
    expect(screen.getByText('HTTP 500')).toBeTruthy()
  })

  it('failed run: shows the error, opens the log and retries with the same questions', async () => {
    const data = aiVisibilityFixture(false, PROMPTS)
    data.log = [
      {
        id: 'final',
        status: 'failed',
        label: 'AI visibility check',
        ms: null,
        at: '',
        detail: { error: 'No AI engine answered.' },
      },
    ]
    await show(auditWith(od('failed', data, 'No AI engine answered. Try again in a minute.')))
    expect(screen.getByText(/Try again in a minute/)).toBeTruthy()
    expect(
      screen.getByRole('button', { name: 'How this check ran' }).getAttribute('aria-expanded'),
    ).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(calls[0]?.data.prompts).toEqual(PROMPTS))
  })
})
