import { useState } from 'react'
import { LogDetails, RunLog } from '@/components/research/AiVisibilityPanel'
import { Chip } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useAiQuestions, useAiRunAnswers, useRunAiReport } from '@/hooks/ai-report'
import type {
  AiMentionRate,
  AiReportMetrics,
  AiVisibility,
  Audit,
  OnDemand,
} from '@/lib/api/research-types'
import { Markdown } from '@/lib/markdown'
import { cn } from '@/lib/utils'
import { useAiDraft } from '@/stores/ai-draft-store'

const pct = (n: number) => `${Math.round(n * 100)}%`

/** "named in 11 of 24 answers (46%, likely 28% to 65%)": the number and how sure we are of it. */
export function mentionText(m: AiMentionRate): string {
  if (m.n === 0) return 'No answers to count yet'
  return `Named in ${m.k} of ${m.n} answers (${pct(m.rate)}, likely ${pct(m.low)} to ${pct(m.high)})`
}

export function duration(ms: number): string {
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

function Failure({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <Alert variant="destructive">
      <AlertDescription>
        {error instanceof Error ? error.message : 'Could not start the report.'}
      </AlertDescription>
    </Alert>
  )
}

/** Distinct, trimmed, non-empty questions: what will really be sent. */
export function approved(list: string[]): string[] {
  return [...new Set(list.map((q) => q.trim().replace(/\s+/g, ' ')).filter(Boolean))]
}

/**
 * The only way to start a report. Step 1 writes the questions (cheap, nothing runs). Step 2 lets
 * the user edit them; only "Approve and run" starts the paid job, with exactly that list.
 */
function Setup({
  audit,
  initial,
  onCancel,
}: {
  audit: Audit
  initial?: string[]
  onCancel?: () => void
}) {
  const write = useAiQuestions(audit.id)
  const run = useRunAiReport(audit.id, audit.domain)
  // The questions being reviewed live in a store, not here: switching tabs must not lose them.
  const draft = useAiDraft((s) => s.drafts[audit.id])
  const list = draft?.list ?? (initial?.length ? initial : null)
  const plan = draft?.plan ?? null
  const setList = (next: string[]) => useAiDraft.getState().setDraft(audit.id, { list: next, plan })
  const generate = () => write.mutate()

  if (list === null) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5">
        <p className="text-[13px] font-semibold">Step 1 of 2: write the questions</p>
        <p className="text-[13px] text-muted-foreground">
          We write the questions a patient might ask an AI assistant about this clinic's services
          and city. You review them next. Nothing is asked to the AI engines until you approve.
        </p>
        <Button disabled={write.isPending} onClick={generate}>
          {write.isPending ? 'Writing questions…' : 'Generate questions'}
        </Button>
        <Failure error={write.error} />
      </div>
    )
  }

  const questions = approved(list)
  const engines = plan?.engines.length ?? 0
  const calls = plan ? questions.length * engines * plan.runs : null
  const tooMany = plan ? questions.length > plan.maxQuestions : false
  const tooBig = plan && calls != null ? calls > plan.maxCalls : false
  return (
    <form
      className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5"
      onSubmit={(e) => {
        e.preventDefault()
        run.mutate(questions)
      }}
    >
      <p className="text-[13px] font-semibold">Step 2 of 2: review the questions</p>
      <p className="text-[13px] text-muted-foreground">
        Edit, remove or add questions. Do not put the clinic's name in them. Nothing is asked until
        you approve.
      </p>
      <ul className="flex flex-col gap-1.5">
        {list.map((q, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: the list is edited in place by position
          <li key={i} className="flex items-center gap-1.5">
            <Input
              aria-label={`Question ${i + 1}`}
              value={q}
              maxLength={200}
              onChange={(e) => setList(list.map((x, j) => (j === i ? e.target.value : x)))}
            />
            <Button
              type="button"
              size="xs"
              variant="outline"
              aria-label={`Remove question ${i + 1}`}
              onClick={() => setList(list.filter((_, j) => j !== i))}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
      <div>
        <Button
          type="button"
          size="xs"
          variant="outline"
          disabled={plan != null && list.length >= plan.maxQuestions}
          onClick={() => setList([...list, ''])}
        >
          Add question
        </Button>
      </div>
      <p className="text-[12px] text-muted-foreground" aria-live="polite">
        {plan
          ? `${questions.length} questions × ${engines} engines × ${plan.runs} repeats = ${calls} answers. It runs in the background and takes a few minutes.`
          : 'Same engines and repeats as the last report.'}
      </p>
      {tooMany ? (
        <p className="text-[12px] text-destructive">
          Too many questions. The limit is {plan?.maxQuestions}.
        </p>
      ) : null}
      {tooBig ? (
        <p className="text-[12px] text-destructive">
          This would make {calls} answers. The limit is {plan?.maxCalls}. Remove some questions.
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          disabled={run.isPending || questions.length === 0 || tooMany || tooBig}
        >
          {run.isPending ? 'Starting…' : 'Approve and run'}
        </Button>
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        ) : (
          <Button type="button" variant="outline" disabled={write.isPending} onClick={generate}>
            Write new questions
          </Button>
        )}
      </div>
      <Failure error={run.error ?? write.error} />
    </form>
  )
}

function Progress({ data }: { data: AiVisibility | null }) {
  const p = data?.progress
  if (!p) return <Skeleton className="h-16 w-full" />
  const events = data?.log ?? []
  const reading = p.phase ? p.phase === 'read' : p.asked >= p.total
  // A stopped run reads fewer answers than were planned: the bar counts what is really left.
  const total = Math.max(reading && p.readTotal ? p.readTotal : p.total, 1)
  const done = reading ? p.judged : p.asked
  return (
    <div className="flex flex-col gap-2">
      <div
        role="status"
        aria-live="polite"
        className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2.5"
      >
        <p className="text-[13px] text-muted-foreground">
          {reading ? 'Reading the answers' : 'Asking the AI engines'} · {done} of {total}
          {p.failed > 0 ? ` · ${p.failed} failed` : ''}
        </p>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-label="Report progress"
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full bg-primary transition-[width] duration-300"
            style={{ width: `${Math.min(100, (done / total) * 100)}%` }}
          />
        </div>
        <p className="text-[12px] text-muted-foreground">
          Cost so far ${p.costUsd.toFixed(2)}. You can close this panel; the report keeps running.
        </p>
      </div>
      {events.length > 0 ? (
        <div className="rounded-lg border border-border bg-card px-3 py-1">
          <RunLog events={events} prompts={data?.prompts ?? []} grouped />
        </div>
      ) : null}
    </div>
  )
}

const LEADERBOARD_ROWS = 10

function Leaderboard({ r }: { r: AiReportMetrics }) {
  // Only brands that were named (and this clinic, always). The rest would be a long list of zeros.
  const named = r.leaderboard.filter((name) => name === r.target || (r.shareOfVoice[name] ?? 0) > 0)
  const shown = named.slice(0, LEADERBOARD_ROWS)
  const hidden = r.leaderboard.length - shown.length
  return (
    <>
      <ol className="flex flex-col gap-1.5" aria-label="Who the engines name">
        {shown.map((name) => {
          const share = r.shareOfVoice[name] ?? 0
          const mine = name === r.target
          return (
            <li key={name} className="text-[13px]">
              <div className="flex items-baseline justify-between gap-2">
                <span className={cn('min-w-0 truncate', mine && 'font-semibold')}>
                  {name}
                  {mine ? ' (this clinic)' : ''}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {pct(share)} of mentions · score {r.perBrand[name]?.VI ?? 0}
                </span>
              </div>
              <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className={cn('h-full', mine ? 'bg-primary' : 'bg-muted-foreground/50')}
                  style={{ width: `${Math.round(share * 100)}%` }}
                />
              </div>
            </li>
          )
        })}
      </ol>
      {hidden > 0 ? (
        <p className="text-[12px] text-muted-foreground">
          {hidden} more brands tracked, with few or no mentions.
        </p>
      ) : null}
    </>
  )
}

type Cell = { engine: string; prompt: number }

function Answers({ runId, cell }: { runId?: string; cell: Cell }) {
  const q = useAiRunAnswers(runId, { engine: cell.engine, prompt: cell.prompt }, true)
  if (q.isPending) return <Skeleton className="h-12 w-full" />
  if (q.isError) return <p className="text-[13px] text-destructive">Could not load the answers.</p>
  const items = q.data.items
  return (
    <ul className="flex max-h-72 flex-col gap-3 overflow-y-auto">
      {items.length === 0 ? (
        <li className="text-[13px] text-muted-foreground">No answers.</li>
      ) : null}
      {items.map((a) => (
        <li key={`${a.engine}-${a.prompt}-${a.run}`} className="text-[13px]">
          <p className="mb-1 text-[12px] text-muted-foreground">
            Answer {a.run}
            {a.sources.length ? ` · ${a.sources.length} sources` : ''}
          </p>
          {a.ok ? (
            <Markdown text={a.text} />
          ) : (
            <p className="text-destructive">{a.error ?? 'Failed'}</p>
          )}
        </li>
      ))}
    </ul>
  )
}

function Grid({
  data,
  r,
  onPick,
  picked,
}: {
  data: AiVisibility
  r: AiReportMetrics
  onPick: (c: Cell) => void
  picked: Cell | null
}) {
  const engines = data.engines.map((e) => e.engine)
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-[12px]">
        <caption className="sr-only">How visible the clinic is, by question and engine</caption>
        <thead>
          <tr>
            <th scope="col" className="text-left font-medium text-muted-foreground">
              Question
            </th>
            {engines.map((e) => (
              <th key={e} scope="col" className="px-1 font-medium text-muted-foreground">
                {e}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.prompts.map((question, p) => (
            <tr key={question}>
              <th scope="row" className="max-w-40 truncate text-left font-normal" title={question}>
                {question}
              </th>
              {engines.map((e) => {
                const v = r.matrix[e]?.[String(p)] ?? 0
                const on = picked?.engine === e && picked.prompt === p
                return (
                  <td key={e} className="p-0">
                    <button
                      type="button"
                      aria-label={`${e}, ${question}: ${pct(v)}`}
                      aria-pressed={on}
                      onClick={() => onPick({ engine: e, prompt: p })}
                      className={cn(
                        'h-7 w-full cursor-pointer rounded border text-[11px]',
                        on ? 'border-primary' : 'border-border',
                      )}
                      style={{
                        backgroundColor: `color-mix(in srgb, var(--color-success) ${Math.round(v * 100)}%, transparent)`,
                      }}
                    >
                      {v > 0 ? pct(v) : '–'}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Report({
  od,
  data,
  audit,
}: {
  od: OnDemand<AiVisibility>
  data: AiVisibility
  audit: Audit
}) {
  const draft = useAiDraft((s) => s.drafts[audit.id])
  const [picked, setPicked] = useState<Cell | null>(null)
  const r = data.report
  if (draft) {
    return <Setup audit={audit} onCancel={() => useAiDraft.getState().clearDraft(audit.id)} />
  }
  if (!r) return null
  const q = data.quality
  const u = data.usage
  return (
    <div className="flex flex-col gap-3">
      <LogDetails events={data.log} prompts={data.prompts} />
      {od.state === 'partial' ? (
        <Alert>
          <AlertDescription>
            {q?.partialReason ?? 'Not enough answers came back.'} The score below is a rough guide,
            not a measurement.
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] text-muted-foreground">Visibility score (0 to 100)</p>
          <p className="text-3xl font-semibold leading-tight">{r.visibilityIndex}</p>
          <p className="text-[13px]">{mentionText(r.mentionRate)}</p>
          {r.gapVsTopCompetitor !== 0 ? (
            <p className="text-[12px] text-muted-foreground">
              {r.gapVsTopCompetitor > 0
                ? `${r.gapVsTopCompetitor} points ahead of the top competitor`
                : `${Math.abs(r.gapVsTopCompetitor)} points behind the top competitor`}
            </p>
          ) : null}
        </div>
        <Button
          size="lg"
          className="shrink-0"
          onClick={() =>
            useAiDraft.getState().setDraft(audit.id, { list: data.prompts, plan: null })
          }
        >
          Run again
        </Button>
      </div>
      <Leaderboard r={r} />
      <ul className="flex flex-wrap gap-1.5">
        {data.engines.map((e) => (
          <li key={e.engine}>
            <Chip tone={e.promptsFailed === e.promptsTotal ? 'warn' : e.mentioned ? 'good' : 'bad'}>
              {e.engine}
              {e.mentionRate ? ` ${e.mentionRate.k}/${e.mentionRate.n}` : ''}
            </Chip>
          </li>
        ))}
      </ul>
      <Grid data={data} r={r} onPick={setPicked} picked={picked} />
      {picked ? (
        <div className="rounded-lg border border-border bg-card px-3 py-2">
          <p className="mb-2 text-[13px] font-semibold">
            {picked.engine} · {data.prompts[picked.prompt]}
          </p>
          <Answers runId={data.runId} cell={picked} />
        </div>
      ) : (
        <p className="text-[12px] text-muted-foreground">Select a square to read the answers.</p>
      )}
      {u ? (
        <p className="text-[12px] text-muted-foreground">
          {u.calls} answers · ${u.costUsd.toFixed(2)} · {duration(u.ms)} · scoring v
          {data.scoringVersion ?? 1}. Scores change a little from run to run; the range shows how
          much.
        </p>
      ) : null}
    </div>
  )
}

/**
 * The AI visibility tab. Step 1 writes the questions, step 2 lets the user approve them, then it
 * shows progress while the report runs and the score, ranking and grid when it ends.
 */
export function AiReportPanel({ audit }: { audit: Audit }) {
  const od = audit.research?.aiVisibility
  if (!od) return null
  const data = od.data
  if (data?.kind !== 'full') {
    // Nothing yet, or an old quick check (not shown: the report replaces it).
    return od.state === 'running' ? <Skeleton className="h-16 w-full" /> : <Setup audit={audit} />
  }
  if (od.state === 'running') return <Progress data={data} />
  if (od.state === 'failed') {
    return (
      <div className="flex flex-col gap-2">
        <Alert variant="destructive">
          <AlertDescription>{od.error ?? 'The report failed.'}</AlertDescription>
        </Alert>
        <Setup audit={audit} initial={data.prompts} />
      </div>
    )
  }
  return <Report od={od} data={data} audit={audit} />
}
