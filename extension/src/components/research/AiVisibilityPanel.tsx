import {
  ChevronRightIcon,
  CircleCheckIcon,
  CircleIcon,
  CircleMinusIcon,
  CircleXIcon,
  LoaderCircleIcon,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import claudeLogo from '@/assets/engines/claude.svg'
import geminiLogo from '@/assets/engines/gemini.svg'
import openaiLogo from '@/assets/engines/openai.svg'
import perplexityLogo from '@/assets/engines/perplexity.svg'
import type { TraceEvent } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

// The audit's own step list (AuditProgress) is not exported, and another change is editing that
// file, so these two small helpers live here. Merge them when that work lands.
const ENGINE_LOGOS: Record<string, string> = {
  chatgpt: openaiLogo,
  openai: openaiLogo,
  gemini: geminiLogo,
  perplexity: perplexityLogo,
  claude: claudeLogo,
}

/** A light wash of each logo color. ChatGPT's mark is black, so its wash follows the text color. */
const _ENGINE_TINT: Record<string, string> = {
  chatgpt: 'border-foreground/20 bg-foreground/[0.08]',
  openai: 'border-foreground/20 bg-foreground/[0.08]',
  gemini: 'border-[#3186FF]/25 bg-[#3186FF]/[0.08]',
  perplexity: 'border-[#22B8CD]/30 bg-[#22B8CD]/[0.1]',
  claude: 'border-[#D97757]/30 bg-[#D97757]/[0.1]',
}

function EngineName({ name, className }: { name: string; className?: string }) {
  const logo = ENGINE_LOGOS[name.trim().toLowerCase()]
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5', className)}>
      {logo ? (
        <img
          src={logo}
          alt=""
          width={20}
          height={20}
          className={cn(
            'size-5 shrink-0',
            (name.trim().toLowerCase() === 'chatgpt' || name.trim().toLowerCase() === 'openai') &&
              'dark:invert',
          )}
        />
      ) : null}
      <span className="min-w-0">{name}</span>
    </span>
  )
}

function duration(ms: number | null): string {
  if (ms == null) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

function StepIcon({ status }: { status: TraceEvent['status'] | 'pending' }) {
  const cls = 'mt-0.5 size-4 shrink-0'
  if (status === 'running')
    return (
      <LoaderCircleIcon aria-label="running" className={cn(cls, 'animate-spin text-primary')} />
    )
  if (status === 'done')
    return <CircleCheckIcon aria-label="done" className={cn(cls, 'text-success')} />
  if (status === 'failed')
    return <CircleXIcon aria-label="failed" className={cn(cls, 'text-destructive')} />
  if (status === 'skipped')
    return <CircleMinusIcon aria-label="skipped" className={cn(cls, 'text-muted-foreground')} />
  return <CircleIcon aria-label="waiting" className={cn(cls, 'text-muted-foreground/50')} />
}

const SOURCE_NOTE: Record<string, string> = {
  local_competitors: 'Google Maps competitors',
  llm: 'named by AI',
  none: 'none found',
}

/** One short line under a step. Detail keys arrive camelCased from the API client. */
function note(e: TraceEvent): string | null {
  const d = e.detail
  if (e.status === 'failed') return typeof d.error === 'string' ? d.error : 'Failed'
  if (e.status === 'skipped') return typeof d.error === 'string' ? d.error : 'Skipped'
  if (e.status !== 'done') return null
  if (e.id === 'prompts') return `${d.count ?? 0} questions`
  if (e.id === 'competitors') {
    return `${SOURCE_NOTE[String(d.source)] ?? d.source}, ${d.count ?? 0} found`
  }
  if (e.id.startsWith('ask:')) {
    // A full report asks each question several times: say how often the clinic was named.
    const runs = typeof d.runs === 'number' ? d.runs : 1
    const named = typeof d.named === 'number' ? d.named : null
    const failed = typeof d.failed === 'number' ? d.failed : 0
    // The judge reads the answers after all questions are asked. Until then nothing is known
    // about who was named, so say nothing rather than "not named".
    if (d.read === false) {
      return [
        typeof d.tokens === 'number' && d.tokens > 0 ? `${d.tokens} tokens` : null,
        failed > 0 ? `${failed} failed` : null,
      ]
        .filter(Boolean)
        .join(' · ')
    }
    return [
      runs > 1 && named != null
        ? named > 0
          ? `Clinic named in ${named} of ${runs} answers`
          : 'Clinic not named'
        : d.mentioned
          ? 'Clinic named'
          : 'Clinic not named',
      d.linked ? 'link to the clinic site' : null,
      typeof d.tokens === 'number' && d.tokens > 0 ? `${d.tokens} tokens` : null,
      failed > 0 ? `${failed} failed` : null,
    ]
      .filter(Boolean)
      .join(' · ')
  }
  return null
}

const engineLabel = (x: Record<string, unknown>): string =>
  typeof x.engine === 'string' ? x.engine : 'Engine'
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const count = (n: number) => n.toLocaleString('en-US')
function money(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.0001) return '<$0.0001'
  return `$${usd.toFixed(4)}`
}

/**
 * The "Cost and tokens" step, shown just before the last step. Input tokens are the text we
 * send to the engine (the question plus web search results); output tokens are what it writes.
 * Detail keys arrive camelCased from the API client.
 */
function UsageRow({ e }: { e: TraceEvent }) {
  const d = e.detail
  const engines = (Array.isArray(d.byEngine) ? d.byEngine : []).filter(
    (x): x is Record<string, unknown> => typeof x === 'object' && x !== null,
  )
  const judge = (d.judge ?? null) as {
    tokens?: unknown
    costUsd?: unknown
    label?: unknown
  } | null
  const failed = num(d.failed)
  return (
    <li className="py-1.5">
      <div className="flex items-start gap-2.5">
        <StepIcon status={e.status} />
        <div className="min-w-0 flex-1">
          <span className="text-[13px] font-semibold">{e.label}</span>
          <p className="text-[13px] tabular-nums">
            <span className="font-semibold">{money(num(d.costUsd))}</span> total ·{' '}
            {count(num(d.tokens))} tokens
          </p>
          <p className="text-[12px] text-muted-foreground tabular-nums">
            {count(num(d.promptTokens))} input · {count(num(d.completionTokens))} output ·{' '}
            {num(d.calls) - failed} answers{failed > 0 ? ` (${failed} failed)` : ''}
            {e.ms != null ? ` · ${duration(e.ms)} in all` : ''}
          </p>
          {engines.length > 0 ? (
            <SmoothDisclosure label="Show breakdown">
              <table className="w-full text-[12px] tabular-nums">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="font-medium">Engine</th>
                    <th className="text-right font-medium">Tokens</th>
                    <th className="text-right font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {engines.map((x) => (
                    <tr key={engineLabel(x)} className="border-t border-border/60">
                      <td className="py-0.5">
                        <EngineName name={engineLabel(x)} />
                      </td>
                      <td className="text-right">{count(num(x.tokens))}</td>
                      <td className="text-right">{money(num(x.costUsd))}</td>
                    </tr>
                  ))}
                  {judge ? (
                    <tr className="border-t border-border/60">
                      <td className="py-0.5">
                        {typeof judge.label === 'string' ? judge.label : 'Competitor check (AI)'}
                      </td>
                      <td className="text-right">{count(num(judge.tokens))}</td>
                      <td className="text-right">{money(num(judge.costUsd))}</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </SmoothDisclosure>
          ) : null}
        </div>
      </div>
    </li>
  )
}

/** `ask:Claude:0` is the first stored question. Older rows only have "question 1" as a label. */
function askedQuestion(event: TraceEvent, prompts: string[]): string | null {
  if (!event.id.startsWith('ask:')) return null
  const saved = event.detail.prompt
  if (typeof saved === 'string' && saved.trim()) return saved.trim()
  const index = Number(event.id.split(':')[2])
  const prompt = Number.isInteger(index) ? prompts[index] : undefined
  return prompt?.trim() || null
}

function StepRow({ e, prompts = [] }: { e: TraceEvent; prompts?: string[] }) {
  if (e.id === 'usage') return <UsageRow e={e} />
  const line = note(e)
  const title = askedQuestion(e, prompts) ?? e.label
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <StepIcon status={e.status} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="flex-1 text-[13px] font-semibold break-words">{title}</span>
          <span className="shrink-0 text-[12px] text-muted-foreground tabular-nums">
            {duration(e.ms)}
          </span>
        </div>
        {line ? (
          <p
            className={cn(
              'text-[12px] text-muted-foreground',
              e.status === 'failed' && 'text-destructive',
            )}
          >
            {line}
          </p>
        ) : null}
      </div>
    </li>
  )
}

function SmoothDisclosure({
  label,
  children,
  defaultOpen = false,
  prominent = false,
  buttonClassName,
}: {
  label: string
  children: ReactNode
  defaultOpen?: boolean
  prominent?: boolean
  buttonClassName?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={prominent ? undefined : 'mt-1.5'}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'flex cursor-pointer items-center gap-1 text-left',
          prominent ? 'w-full gap-1.5 text-[13px] font-semibold' : 'text-[12px] text-primary',
          buttonClassName,
        )}
      >
        <ChevronRightIcon
          aria-hidden="true"
          className={cn(
            'shrink-0 transition-transform duration-200 ease-out',
            prominent ? 'size-4' : 'size-3.5',
            open && 'rotate-90',
          )}
        />
        {label}
      </button>
      <div
        className={cn(
          'grid transition-[grid-template-rows,opacity] duration-300 ease-out',
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
      >
        <div className="overflow-hidden">
          <div className="pt-1.5">{children}</div>
        </div>
      </div>
    </div>
  )
}

function engineName(event: TraceEvent): string {
  const name = event.id.split(':')[1]
  return name || event.label
}

function groupStatus(events: TraceEvent[]): TraceEvent['status'] | 'pending' {
  if (events.some((event) => event.status === 'running')) return 'running'
  if (events.some((event) => event.status === 'failed')) return 'failed'
  if (events.every((event) => event.status === 'done' || event.status === 'skipped')) return 'done'
  return 'pending'
}

/** One row per engine. The questions sit in a dropdown, the same shape as chosen pages. */
function AskGroups({ events, prompts }: { events: TraceEvent[]; prompts: string[] }) {
  const grouped = new Map<string, TraceEvent[]>()
  for (const event of events) {
    const name = engineName(event)
    grouped.set(name, [...(grouped.get(name) ?? []), event])
  }
  return (
    <>
      {[...grouped.entries()].map(([name, items]) => {
        const times = items.flatMap((event) => (event.ms == null ? [] : [event.ms]))
        const ms = times.length > 0 ? Math.max(...times) : null
        const named = items.filter((event) => event.detail.mentioned).length
        return (
          <li key={name} className="py-1.5">
            <div className="flex items-start gap-2.5">
              <StepIcon status={groupStatus(items)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <EngineName name={name} className="flex-1 text-[13px] font-semibold" />
                  <span className="shrink-0 text-[12px] text-muted-foreground tabular-nums">
                    {duration(ms)}
                  </span>
                </div>
                <p className="text-[12px] text-muted-foreground">
                  {items.some((event) => event.detail.read === false)
                    ? 'Who was named is shown after the answers are read'
                    : `${named} of ${items.length} questions named the clinic`}
                </p>
                <SmoothDisclosure label="Show questions">
                  <ol>
                    {items.map((event) => (
                      <StepRow key={event.id} e={event} prompts={prompts} />
                    ))}
                  </ol>
                </SmoothDisclosure>
              </div>
            </div>
          </li>
        )
      })}
    </>
  )
}

/** The server folds the log (one entry per step), so this only draws it. */
export function RunLog({
  events,
  prompts = [],
  grouped = false,
}: {
  events: TraceEvent[]
  prompts?: string[]
  grouped?: boolean
}) {
  const asks = events.filter((event) => event.id.startsWith('ask:'))
  let asksDrawn = false
  return (
    <ol className="divide-y divide-border/60" aria-label="AI visibility steps">
      {events.map((event) => {
        if (!grouped || !event.id.startsWith('ask:')) return <StepRow key={event.id} e={event} />
        if (asksDrawn) return null
        asksDrawn = true
        return <AskGroups key="asks" events={asks} prompts={prompts} />
      })}
    </ol>
  )
}

export function LogDetails({
  events,
  prompts = [],
  open,
}: {
  events: TraceEvent[]
  prompts?: string[]
  open?: boolean
}) {
  if (events.length === 0) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-card-foreground">
      <SmoothDisclosure label="How this check ran" defaultOpen={open} prominent>
        <RunLog events={events} prompts={prompts} grouped />
      </SmoothDisclosure>
    </div>
  )
}
