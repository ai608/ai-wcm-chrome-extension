import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import {
  aiQuestionsFixture,
  aiReportFixture,
  aiRunAnswersFixture,
} from '@/lib/api/mock/ai-report-fixture'
import { aiVisibilityFixture, buildAudit } from '@/lib/api/mock/research-fixtures'
import type { AiVisibility, Audit, OnDemand } from '@/lib/api/research-types'

const calls: { key: string; data: Record<string, unknown> }[] = []
let plan = aiQuestionsFixture()
let failWith: string | null = null
let holdQuestions: Promise<void> | null = null
vi.mock('@/lib/messaging', () => ({
  call: async (key: string, data: Record<string, unknown> = {}) => {
    calls.push({ key, data })
    if (failWith) throw new Error(failWith)
    if (key === 'getAiQuestions' && holdQuestions) await holdQuestions
    if (key === 'getAiQuestions') return plan
    if (key === 'getAiRunAnswers') {
      return aiRunAnswersFixture(
        data.engine as string | undefined,
        data.prompt as number | undefined,
      )
    }
    return null
  },
}))

function auditWith(od: OnDemand<AiVisibility>): Audit {
  const a = buildAudit('aud_rep', 'glow.com', 'https://glow.com/', new Date())
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
  const { AiReportPanel } = await import('@/components/research/AiReportPanel')
  return render(
    <Providers>
      <AiReportPanel audit={audit} />
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
  plan = aiQuestionsFixture()
  failWith = null
  holdQuestions = null
  const { useAiDraft } = await import('@/stores/ai-draft-store')
  useAiDraft.setState({ drafts: {} })
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('helpers', () => {
  it('says the number and how sure it is, and handles no answers', async () => {
    const { mentionText, duration } = await import('@/components/research/AiReportPanel')
    expect(mentionText({ k: 11, n: 24, rate: 0.458, low: 0.275, high: 0.65 })).toBe(
      'Named in 11 of 24 answers (46%, likely 28% to 65%)',
    )
    expect(mentionText({ k: 0, n: 0, rate: 0, low: 0, high: 0 })).toBe('No answers to count yet')
    expect(duration(45_000)).toBe('45 s')
    expect(duration(142_000)).toBe('2 min 22 s')
  })

  it('polls a running full report for longer than a normal audit', async () => {
    const { pollCapFor, POLL_CAP_MS, REPORT_POLL_CAP_MS } = await import('@/hooks/research-queries')
    const full = aiReportFixture(true)
    expect(pollCapFor(auditWith(od('running', full)))).toBe(REPORT_POLL_CAP_MS)
    expect(pollCapFor(auditWith(od('running', aiVisibilityFixture(true, ['a']))))).toBe(POLL_CAP_MS)
    expect(pollCapFor(auditWith(od('ready', full)))).toBe(POLL_CAP_MS)
    expect(pollCapFor(null)).toBe(POLL_CAP_MS)
  })
})

describe('full AI report panel', () => {
  it('step 1: only offers to write the questions; nothing is asked or started', async () => {
    await show(auditWith(od('not_run', null)))
    expect(screen.getByText('Step 1 of 2: write the questions')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Approve and run' })).toBeNull()
    expect(calls).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByText('Step 2 of 2: review the questions')
    expect(calls.map((c) => c.key)).toEqual(['getAiQuestions'])
    expect(calls.some((c) => c.key === 'runAiReport')).toBe(false)
  })

  it('step 2: shows the written questions and the size of the run', async () => {
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 6')
    expect((screen.getByLabelText('Question 1') as HTMLInputElement).value).toBe(
      'best botox in Austin, TX',
    )
    expect(screen.getByText(/6 questions × 4 engines × 2 repeats = 48 answers/)).toBeTruthy()
  })

  it('approval sends exactly the edited list: edits kept, removed gone, blanks and repeats dropped', async () => {
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 6')
    fireEvent.change(screen.getByLabelText('Question 1'), {
      target: { value: '  best   botox near me ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add question' }))
    fireEvent.change(screen.getByLabelText('Question 6'), {
      target: { value: 'best botox near me' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add question' }))
    expect(calls.some((c) => c.key === 'runAiReport')).toBe(false) // still nothing started
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'runAiReport')).toBe(true))
    expect(calls.find((c) => c.key === 'runAiReport')).toEqual({
      key: 'runAiReport',
      data: {
        auditId: 'aud_rep',
        prompts: [
          'best botox near me',
          'top rated med spa in Austin, TX',
          'how much does laser hair removal cost in Austin, TX',
          'IV therapy reviews in Austin, TX',
          'most trusted med spa for weight loss in Austin, TX',
        ],
      },
    })
  })

  it('cannot approve an empty list; blank questions do not count; the list cannot outgrow the limit', async () => {
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 6')
    const approve = () =>
      screen.getByRole('button', { name: 'Approve and run' }) as HTMLButtonElement
    for (let i = 6; i >= 1; i--) {
      fireEvent.click(screen.getByRole('button', { name: `Remove question ${i}` }))
    }
    expect(approve().disabled).toBe(true) // empty list
    for (let i = 0; i < 6; i++)
      fireEvent.click(screen.getByRole('button', { name: 'Add question' }))
    for (let i = 1; i <= 6; i++) {
      fireEvent.change(screen.getByLabelText(`Question ${i}`), {
        target: { value: `question ${i}` },
      })
    }
    expect(approve().disabled).toBe(false)
    for (let i = 0; i < 6; i++)
      fireEvent.click(screen.getByRole('button', { name: 'Add question' }))
    // the list is at the limit (12): adding more is not possible
    expect(
      (screen.getByRole('button', { name: 'Add question' }) as HTMLButtonElement).disabled,
    ).toBe(true)
    // twelve blank questions are not questions
    expect(screen.getByText(/6 questions × 4 engines × 2 repeats = 48 answers/)).toBeTruthy()
    expect(calls.some((c) => c.key === 'runAiReport')).toBe(false)
  })

  it('cannot approve a run bigger than the call limit, and says why', async () => {
    plan = { ...plan, maxCalls: 20 } // 6 questions x 4 engines x 2 repeats = 48 answers
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 1')
    expect(screen.getByText(/This would make 48 answers\. The limit is 20/)).toBeTruthy()
    const approve = screen.getByRole('button', { name: 'Approve and run' }) as HTMLButtonElement
    expect(approve.disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 6' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 5' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 4' }))
    // 3 x 4 x 2 = 24: still over 20; remove one more -> 16
    expect(approve.disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 3' }))
    expect(approve.disabled).toBe(false)
  })

  it('"Write new questions" asks the writer again', async () => {
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 1')
    fireEvent.click(screen.getByRole('button', { name: 'Write new questions' }))
    await waitFor(() => expect(calls.filter((c) => c.key === 'getAiQuestions')).toHaveLength(2))
  })

  it('an old quick check is not shown: the user starts at step 1', async () => {
    await show(auditWith(od('ready', aiVisibilityFixture(true, ['a']))))
    expect(screen.getByText('Step 1 of 2: write the questions')).toBeTruthy()
    expect(screen.queryByText(/was named in/)).toBeNull()
  })

  it('a quick check that is still running shows no start controls', async () => {
    await show(auditWith(od('running', aiVisibilityFixture(true, ['a']))))
    expect(screen.queryByRole('button', { name: 'Generate questions' })).toBeNull()
  })

  it('running: shows asked-of-total, then the reading phase, and the cost so far', async () => {
    const base = aiReportFixture(true)
    const asking = {
      ...base,
      progress: { total: 48, asked: 12, failed: 1, judged: 0, costUsd: 0.07 },
    }
    const { unmount } = await show(auditWith(od('running', asking)))
    expect(screen.getByRole('status').textContent).toContain(
      'Asking the AI engines · 12 of 48 · 1 failed',
    )
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('12')
    expect(screen.getByRole('status').textContent).toContain('$0.07')
    unmount()
    const reading = {
      ...base,
      progress: { total: 48, asked: 48, failed: 0, judged: 30, costUsd: 0.2 },
    }
    await show(auditWith(od('running', reading)))
    expect(screen.getByRole('status').textContent).toContain('Reading the answers · 30 of 48')
  })

  it('running with no progress yet shows a placeholder, not a crash', async () => {
    const seed = { ...aiReportFixture(true), progress: undefined, report: undefined }
    await show(auditWith(od('running', seed)))
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('ready: score, how sure we are, ranking, engines and cost', async () => {
    await show(auditWith(od('ready', aiReportFixture(true))))
    expect(screen.getByText('31.4')).toBeTruthy()
    expect(screen.getByText('Named in 11 of 24 answers (46%, likely 28% to 65%)')).toBeTruthy()
    expect(screen.getByText('4.1 points ahead of the top competitor')).toBeTruthy()
    const ranking = screen.getByRole('list', { name: 'Who the engines name' })
    expect(
      within(ranking)
        .getAllByRole('listitem')
        .map((li) => li.textContent?.split(' ')[0]),
    ).toEqual(['Glow', 'Revive', 'Skin', 'The'])
    expect(within(ranking).getByText(/\(this clinic\)/)).toBeTruthy()
    expect(screen.getByText(/48 answers · \$0\.31 · 2 min 22 s · scoring v1/)).toBeTruthy()
    expect(screen.queryByText(/rough guide/)).toBeNull()
  })

  it('a weak clinic is shown behind its rivals', async () => {
    await show(auditWith(od('ready', aiReportFixture(false))))
    expect(screen.getByText('38.5 points behind the top competitor')).toBeTruthy()
  })

  it('partial: warns that the score is a rough guide and says why', async () => {
    const data = aiReportFixture(true)
    data.quality = {
      ...(data.quality as NonNullable<typeof data.quality>),
      partialReason: 'Only 55% of the answers came back.',
    }
    await show(auditWith(od('partial', data)))
    expect(
      screen.getByText(/Only 55% of the answers came back\. The score below is a rough guide/),
    ).toBeTruthy()
  })

  it('grid: one square per question and engine; selecting one loads just those answers', async () => {
    await show(auditWith(od('ready', aiReportFixture(true))))
    const cells = screen.getAllByRole('button', { name: /^(ChatGPT|Gemini|Perplexity|Claude), / })
    expect(cells).toHaveLength(6 * 4)
    expect(screen.getByText('Select a square to read the answers.')).toBeTruthy()
    fireEvent.click(
      screen.getByRole('button', { name: /^Gemini, top rated med spa in Austin, TX/ }),
    )
    await waitFor(() => expect(calls.some((c) => c.key === 'getAiRunAnswers')).toBe(true))
    expect(calls.find((c) => c.key === 'getAiRunAnswers')?.data).toEqual({
      runId: 'mock-run',
      engine: 'Gemini',
      prompt: 2,
    })
    await screen.findByText(/Answer 1/)
    expect(screen.getByText(/people often pick Revive Medical Spa/)).toBeTruthy()
  })

  it('failed: shows the reason and the previous questions, ready to approve again', async () => {
    await show(
      auditWith(
        od('failed', { ...aiReportFixture(true), report: undefined }, 'No AI engine answered.'),
      ),
    )
    expect(screen.getByText('No AI engine answered.')).toBeTruthy()
    expect((screen.getByLabelText('Question 1') as HTMLInputElement).value).toBe(
      'best botox in Austin, TX',
    )
    expect(calls.some((c) => c.key === 'runAiReport')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'runAiReport')).toBe(true))
  })

  it('"Run again" goes back to review with the same questions; Cancel returns to the report', async () => {
    await show(auditWith(od('ready', aiReportFixture(true))))
    fireEvent.click(screen.getByRole('button', { name: 'Run again' }))
    expect(screen.getByText('Step 2 of 2: review the questions')).toBeTruthy()
    expect((screen.getByLabelText('Question 3') as HTMLInputElement).value).toBe(
      'top rated med spa in Austin, TX',
    )
    expect(calls).toEqual([]) // no new questions written, nothing started
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByText('Visibility score (0 to 100)')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Run again' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'runAiReport')).toBe(true))
    expect(calls.find((c) => c.key === 'runAiReport')?.data.prompts).toHaveLength(6)
  })

  it('a start error is shown, not swallowed', async () => {
    failWith = 'This run would make 500 calls; the limit is 400.'
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    expect(await screen.findByText(/limit is 400/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Generate questions' })).toBeTruthy() // can retry
  })
})

describe('AI tab', () => {
  async function tab(audit: Audit) {
    const { Providers } = await import('@/app/providers')
    const { ResearchSubTabs } = await import('@/components/research/ResearchSubTabs')
    const { usePanelStore } = await import('@/stores/panel-store')
    usePanelStore.setState({ researchSubTab: { research: 'ai' } })
    return render(
      <Providers>
        <ResearchSubTabs audit={audit} />
      </Providers>,
    )
  }

  it('before any run: step 1 only, no quick check', async () => {
    await tab(auditWith(od('not_run', null)))
    expect(screen.getByRole('button', { name: 'Generate questions' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Check AI visibility' })).toBeNull()
  })

  it('once a full report exists, the report is shown and nothing else', async () => {
    await tab(auditWith(od('ready', aiReportFixture(true))))
    expect(screen.getByText('Visibility score (0 to 100)')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Check AI visibility' })).toBeNull()
    expect(screen.getByRole('button', { name: 'How this check ran' })).toBeTruthy() // the log is part of it
  })
})

describe('the questions survive switching tabs', () => {
  async function tab(audit: Audit) {
    const { Providers } = await import('@/app/providers')
    const { ResearchSubTabs } = await import('@/components/research/ResearchSubTabs')
    const { usePanelStore } = await import('@/stores/panel-store')
    usePanelStore.setState({ researchSubTab: { research: 'ai' } })
    const view = render(
      <Providers>
        <ResearchSubTabs audit={audit} />
      </Providers>,
    )
    return { view, usePanelStore }
  }

  it('after Local Competitors and back, the edited questions are still there', async () => {
    const audit = auditWith(od('not_run', null))
    const { usePanelStore } = await tab(audit)
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 6')
    fireEvent.change(screen.getByLabelText('Question 1'), {
      target: { value: 'my own edited question' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 2' }))

    fireEvent.click(screen.getByRole('button', { name: 'Local Competitors' }))
    expect(screen.queryByLabelText('Question 1')).toBeNull() // the AI panel is really gone
    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))

    expect(screen.getByText('Step 2 of 2: review the questions')).toBeTruthy()
    expect((screen.getByLabelText('Question 1') as HTMLInputElement).value).toBe(
      'my own edited question',
    )
    expect(screen.getAllByLabelText(/^Question \d$/)).toHaveLength(5) // the removed one stays removed
    expect(screen.getByText(/5 questions × 4 engines × 2 repeats = 40 answers/)).toBeTruthy()
    expect(calls.filter((c) => c.key === 'getAiQuestions')).toHaveLength(1) // not written again
    expect(usePanelStore.getState().researchSubTab.research).toBe('ai')
  })

  it('also survives the whole panel being unmounted and mounted again', async () => {
    const audit = auditWith(od('not_run', null))
    const first = await tab(audit)
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 6')
    first.view.unmount()
    await tab(audit)
    expect((screen.getByLabelText('Question 6') as HTMLInputElement).value).toBe(
      'most trusted med spa for weight loss in Austin, TX',
    )
  })

  it('questions that finish writing while the user is on another tab are not lost', async () => {
    let release: () => void = () => {}
    holdQuestions = new Promise<void>((r) => {
      release = r
    })
    const { useAiDraft } = await import('@/stores/ai-draft-store')
    await tab(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Local Competitors' })) // leave while writing
    release()
    await waitFor(() => expect(useAiDraft.getState().drafts.aud_rep?.list).toHaveLength(6))
    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))
    expect(screen.getByText('Step 2 of 2: review the questions')).toBeTruthy()
  })

  it('approving spends the draft; Cancel on a re-run drops it; another audit has its own', async () => {
    const { useAiDraft } = await import('@/stores/ai-draft-store')
    await show(auditWith(od('not_run', null)))
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await screen.findByLabelText('Question 1')
    expect(Object.keys(useAiDraft.getState().drafts)).toEqual(['aud_rep'])
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'runAiReport')).toBe(true))
    await waitFor(() => expect(useAiDraft.getState().drafts).toEqual({}))
    cleanup()

    await show(auditWith(od('ready', aiReportFixture(true))))
    fireEvent.click(screen.getByRole('button', { name: 'Run again' }))
    expect(useAiDraft.getState().drafts.aud_rep?.list).toHaveLength(6)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(useAiDraft.getState().drafts).toEqual({})
    expect(screen.getByText('Visibility score (0 to 100)')).toBeTruthy()
  })

  it('a re-run being reviewed survives a tab switch too', async () => {
    const { usePanelStore } = await import('@/stores/panel-store')
    const { Providers } = await import('@/app/providers')
    const { ResearchSubTabs } = await import('@/components/research/ResearchSubTabs')
    usePanelStore.setState({ researchSubTab: { research: 'ai' } })
    render(
      <Providers>
        <ResearchSubTabs audit={auditWith(od('ready', aiReportFixture(true)))} />
      </Providers>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Run again' }))
    fireEvent.change(screen.getByLabelText('Question 1'), {
      target: { value: 'edited for the re-run' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Local Competitors' }))
    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))
    expect((screen.getByLabelText('Question 1') as HTMLInputElement).value).toBe(
      'edited for the re-run',
    )
  })
})

describe('the run log (how the check ran)', () => {
  const running = () => ({
    ...aiReportFixture(true),
    progress: { total: 48, asked: 20, failed: 0, judged: 0, costUsd: 0.1 },
    report: undefined,
  })

  it('while running: every engine is a row with its questions, tokens and result', async () => {
    await show(auditWith(od('running', running())))
    expect(screen.getByRole('progressbar')).toBeTruthy() // the bar stays
    const log = screen.getByRole('list', { name: 'AI visibility steps' })
    // one row per engine, grouped as before
    for (const engine of ['ChatGPT', 'Gemini', 'Perplexity', 'Claude']) {
      expect(within(log).getAllByText(engine).length).toBeGreaterThan(0)
    }
    expect(within(log).getAllByText(/of 6 questions named the clinic/)).toHaveLength(4)
    fireEvent.click(
      within(log).getAllByRole('button', { name: 'Show questions' })[0] as HTMLElement,
    )
    expect(within(log).getAllByText('best botox in Austin, TX').length).toBeGreaterThan(0)
    // a question asked twice says how often the clinic was named, with tokens
    expect(
      within(log).getAllByText(
        /Clinic named in 1 of 2 answers · link to the clinic site · 1200 tokens/,
      ).length,
    ).toBeGreaterThan(0)
  })

  it('while running, the log is not inside the live progress message', async () => {
    await show(auditWith(od('running', running())))
    expect(within(screen.getByRole('status')).queryByRole('list')).toBeNull()
  })

  it('a started report with no log yet still shows the bar', async () => {
    await show(auditWith(od('running', { ...running(), log: [] })))
    expect(screen.getByRole('progressbar')).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'AI visibility steps' })).toBeNull()
  })

  it('finished: "How this check ran" is there, closed, and opens to the steps and the cost', async () => {
    await show(auditWith(od('ready', aiReportFixture(true))))
    const toggle = screen.getByRole('button', { name: 'How this check ran' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const log = screen.getByRole('list', { name: 'AI visibility steps' })
    expect(within(log).getByText('Questions')).toBeTruthy()
    expect(within(log).getByText('Reading the answers')).toBeTruthy()
    expect(within(log).getByText('Cost and tokens')).toBeTruthy()
    expect(within(log).getByText('$0.3100')).toBeTruthy()
    fireEvent.click(within(log).getByRole('button', { name: 'Show breakdown' }))
    expect(within(log).getByText('Reading the answers (AI)')).toBeTruthy() // what the judge row is
  })

  it('shows failed and cut-short steps with the reason', async () => {
    const data = aiReportFixture(true)
    data.log = data.log.map((e) =>
      e.id === 'ask:Gemini:0'
        ? { ...e, status: 'failed', detail: { error: 'HTTP 429', runs: 2, failed: 2 } }
        : e.id === 'ask:Claude:5'
          ? { ...e, status: 'skipped', detail: { error: 'Stopped at the cost cap', runs: 1 } }
          : e,
    )
    await show(auditWith(od('partial', data)))
    fireEvent.click(screen.getByRole('button', { name: 'How this check ran' }))
    const log = screen.getByRole('list', { name: 'AI visibility steps' })
    for (const b of within(log).getAllByRole('button', { name: 'Show questions' }))
      fireEvent.click(b)
    expect(within(log).getByText('HTTP 429')).toBeTruthy()
    expect(within(log).getByText('Stopped at the cost cap')).toBeTruthy()
  })
})
