import type {
  AiQuestions,
  AiReportMetrics,
  AiRunAnswers,
  AiVisibility,
} from '@/lib/api/research-types'

const ENGINES = ['ChatGPT', 'Gemini', 'Perplexity', 'Claude']
const RIVALS = ['Revive Medical Spa', 'Skin Lab Austin', 'The IV Bar']
const QUESTIONS = [
  'best botox in Austin, TX',
  'who should I see for fillers near Austin, TX',
  'top rated med spa in Austin, TX',
  'how much does laser hair removal cost in Austin, TX',
  'IV therapy reviews in Austin, TX',
  'most trusted med spa for weight loss in Austin, TX',
]

export function aiQuestionsFixture(): AiQuestions {
  return {
    prompts: QUESTIONS,
    source: 'llm',
    engines: ENGINES,
    runs: 2,
    maxQuestions: 12,
    maxCalls: 400,
  }
}

/** A finished full report. `strong` clinics are named more often. Same numbers every time. */
export function aiReportFixture(strong: boolean): AiVisibility {
  const brand = 'Glow Aesthetics Med Spa'
  const cell = (e: number, p: number) =>
    strong ? Math.max(0, 0.62 - e * 0.1 - (p % 3) * 0.12) : (e + p) % 5 === 0 ? 0.18 : 0
  const matrix: AiReportMetrics['matrix'] = Object.fromEntries(
    ENGINES.map((name, e) => [
      name,
      Object.fromEntries(QUESTIONS.map((_, p) => [String(p), cell(e, p)])),
    ]),
  )
  const rate = strong
    ? { k: 11, n: 24, rate: 0.458, low: 0.275, high: 0.65 }
    : { k: 2, n: 24, rate: 0.083, low: 0.023, high: 0.26 }
  const report: AiReportMetrics = {
    target: brand,
    visibilityIndex: strong ? 31.4 : 4.2,
    mentionRate: rate,
    shareOfVoice: strong
      ? {
          [brand]: 0.41,
          [RIVALS[0] as string]: 0.33,
          [RIVALS[1] as string]: 0.18,
          [RIVALS[2] as string]: 0.08,
        }
      : {
          [brand]: 0.07,
          [RIVALS[0] as string]: 0.46,
          [RIVALS[1] as string]: 0.31,
          [RIVALS[2] as string]: 0.16,
        },
    perBrand: {},
    leaderboard: strong ? [brand, ...RIVALS] : [...RIVALS, brand],
    gapVsTopCompetitor: strong ? 4.1 : -38.5,
    coverage: strong ? 0.83 : 0.33,
    citationRate: strong ? 0.25 : 0,
    sentimentIndex: strong ? 0.6 : 0.2,
    sentimentBreakdown: strong
      ? { positive: 0.7, neutral: 0.3, negative: 0 }
      : { positive: 0, neutral: 1, negative: 0 },
    matrix,
    promptAnalytics: QUESTIONS.map((_, i) => ({
      promptId: i,
      avgVisibility: strong ? 0.4 - (i % 3) * 0.1 : 0.04,
      mentionRate: strong ? 0.75 - (i % 3) * 0.25 : 0.1,
    })),
  }
  const now = new Date().toISOString()
  return {
    version: 1,
    kind: 'full',
    runId: 'mock-run',
    scoringVersion: 1,
    brand,
    prompts: QUESTIONS,
    engines: ENGINES.map((engine, i) => ({
      engine,
      model: `mock/${engine.toLowerCase()}`,
      cited: strong && i < 3,
      mentioned: strong && i < 3,
      linked: strong && i === 0,
      promptsMentioned: strong ? 4 - i : 0,
      promptsTotal: 6,
      promptsFailed: 0,
      citedBusinesses: RIVALS,
      answerExcerpt: '',
      error: null,
      answers: [],
      mentionRate: strong
        ? { k: 4 - i, n: 6, rate: (4 - i) / 6, low: 0.2, high: 0.9 }
        : { k: 0, n: 6, rate: 0, low: 0, high: 0.39 },
    })),
    competitors: { source: 'local_competitors', names: RIVALS },
    quality: {
      calls: 48,
      ok: 48,
      failed: 0,
      skipped: 0,
      successRate: 1,
      capped: false,
      partialReason: null,
      judgeFailed: 0,
    },
    progress: { total: 48, asked: 48, failed: 0, judged: 48, costUsd: 0.31 },
    report,
    usage: { calls: 48, failed: 0, tokens: 61_200, costUsd: 0.31, ms: 142_000 },
    log: [
      {
        id: 'prompts',
        status: 'done',
        label: 'Questions',
        ms: 1800,
        at: now,
        detail: { count: 6 },
      },
      {
        id: 'competitors',
        status: 'done',
        label: 'Competitors to compare',
        ms: null,
        at: now,
        detail: { source: 'local_competitors', count: 3 },
      },
      ...ENGINES.flatMap((engine, i) =>
        QUESTIONS.map((_, p) => ({
          id: `ask:${engine}:${p}`,
          status: 'done' as const,
          label: `${engine} · question ${p + 1}`,
          ms: 6000 + p * 700,
          at: now,
          detail: {
            read: true,
            mentioned: strong && i < 3,
            linked: strong && i === 0,
            named: strong && i < 3 ? 1 : 0,
            runs: 2,
            failed: 0,
            tokens: 1200,
            costUsd: 0.0021,
            sources: 4,
          },
        })),
      ),
      {
        id: 'read',
        status: 'done',
        label: 'Reading the answers',
        ms: 22_000,
        at: now,
        detail: { total: 48, done: 48 },
      },
      {
        id: 'usage',
        status: 'done',
        label: 'Cost and tokens',
        ms: 142_000,
        at: now,
        detail: {
          calls: 48,
          failed: 0,
          tokens: 61_200,
          promptTokens: 40_000,
          completionTokens: 21_200,
          costUsd: 0.31,
          byEngine: ENGINES.map((engine) => ({ engine, tokens: 14_000, costUsd: 0.07 })),
          judge: { label: 'Reading the answers (AI)', tokens: 5200, costUsd: 0.03 },
        },
      },
      {
        id: 'final',
        status: 'done',
        label: 'AI visibility check',
        ms: null,
        at: now,
        detail: { outcome: 'ready' },
      },
    ],
  }
}

export function aiRunAnswersFixture(engine?: string, prompt?: number): AiRunAnswers {
  const items = ENGINES.filter((e) => !engine || e === engine).flatMap((e) =>
    QUESTIONS.map((_, p) => p)
      .filter((p) => prompt == null || p === prompt)
      .map((p) => ({
        prompt: p,
        engine: e,
        run: 1,
        ok: true,
        text: `For ${QUESTIONS[p]}, people often pick ${RIVALS[0]} and Glow Aesthetics Med Spa.`,
        sources: ['https://example.com/best-med-spas'],
        error: null,
      })),
  )
  return { prompts: QUESTIONS, items }
}
