import {
  ChevronRightIcon,
  CircleCheckIcon,
  CircleIcon,
  CircleMinusIcon,
  CircleXIcon,
  LoaderCircleIcon,
} from 'lucide-react'
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { SectionTitle } from '@/components/research/shared'
import { UsageStep } from '@/components/research/UsageStep'
import type { Audit, TraceEvent } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

const STEPS: { id: string; label: string }[] = [
  { id: 'home', label: 'Fetch home page' },
  { id: 'analyze', label: 'Analyse home page' },
  { id: 'map', label: 'Find pages' },
  { id: 'pick', label: 'Choose pages to read' },
  { id: 'scrape', label: 'Read pages' },
  { id: 'enrich', label: 'Build site facts' },
  { id: 'probe', label: 'Check links and redirects' },
  { id: 'onpage', label: 'Check every page' },
  { id: 'ai', label: 'AI page analysis' },
  { id: 'gbp', label: 'Google Business Profile' },
  { id: 'psi', label: 'PageSpeed' },
  { id: 'score', label: 'Score the audit' },
  { id: 'usage', label: 'Cost and tokens' },
]

const GROUP_LABEL: Record<string, string> = {
  service: 'Service pages',
  city: 'City pages',
  proof: 'Proof pages',
  trust: 'Trust pages',
  blog: 'Blog',
}

/** Last event per id wins; order is the order each id first appeared. */
export function foldTrace(events: TraceEvent[]): Map<string, TraceEvent> {
  const out = new Map<string, TraceEvent>()
  for (const e of events) out.set(e.id, e)
  return out
}

const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)
const text = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)

function duration(ms: number | null): string {
  if (ms == null) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

function pathOf(url: string): string {
  try {
    const u = new URL(url)
    return `${u.pathname}${u.search}` || '/'
  } catch {
    return url
  }
}

function Icon({ status }: { status: TraceEvent['status'] | 'pending' }) {
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

function summary(step: string, e: TraceEvent, steps: Map<string, TraceEvent>): string | null {
  const d = e.detail
  if (e.status === 'failed') return text(d.error) ?? 'Failed'
  if (e.status === 'skipped') return text(d.reason) ?? 'Skipped'
  if (e.status === 'running') return step === 'scrape' ? readCount(steps) : null
  switch (step) {
    case 'home': {
      const size = num(d.size)
      const via =
        d.via === 'firecrawl'
          ? `Blocked directly${text(d.reason) ? ` (${text(d.reason)})` : ''}, fetched with Firecrawl`
          : 'Fetched directly'
      return `${via}${size ? ` · ${Math.max(1, Math.round(size / 1024))} KB` : ''}`
    }
    case 'probe': {
      const late = num(d.timedOut) ?? 0
      return `${num(d.checked) ?? 0} requests made${late > 0 ? `, ${late} not finished in time` : ''}`
    }
    case 'onpage':
      return `${num(d.pages) ?? 0} pages checked, score ${num(d.score) ?? '-'}`
    case 'map':
      return `${num(d.count) ?? 0} URLs found`
    case 'pick':
      return `${num(d.total) ?? 0} pages chosen`
    case 'scrape':
      return [
        `${num(d.ok) ?? 0} read`,
        `${num(d.failed) ?? 0} failed`,
        ...((num(d.duplicates) ?? 0) + (num(d.skipped) ?? 0) > 0
          ? [`${(num(d.duplicates) ?? 0) + (num(d.skipped) ?? 0)} repeats left out`]
          : []),
      ].join(', ')
    case 'enrich':
      return `${num(d.pages) ?? 0} pages used`
    case 'ai':
      return `${num(d.pages) ?? 0} pages analysed`
    case 'gbp':
      return d.matched ? 'Profile found' : 'No matching profile'
    case 'psi': {
      // Newer audits report `mobile` and `desktop`; older ones only `performance` (mobile).
      const mobile = num(d.mobile) ?? num(d.performance)
      const desktop = num(d.desktop)
      if (mobile == null) return null
      return desktop == null
        ? `Mobile performance ${mobile}`
        : `Performance: mobile ${mobile}, desktop ${desktop}`
    }
    case 'score':
      return num(d.score) != null ? `${num(d.score)} / 100 (${text(d.grade) ?? '-'})` : 'Not scored'
    default:
      return null
  }
}

function readCount(steps: Map<string, TraceEvent>): string | null {
  const total = num(steps.get('pick')?.detail.total)
  let seen = 0
  for (const e of steps.values()) if (e.id.startsWith('page:') && e.status !== 'running') seen++
  return total == null ? null : `${seen}/${total} pages read`
}

function PickGroups({ event }: { event: TraceEvent }) {
  const groups = Array.isArray(event.detail.groups)
    ? (event.detail.groups as { name: string; found: number; picked: string[]; skipped: number }[])
    : []
  if (!groups.some((g) => g.found > 0)) return null
  return (
    <details className="group/pages mt-1.5 text-[12px]">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-primary [&::-webkit-details-marker]:hidden [&::marker]:content-none">
        <ChevronRightIcon
          aria-hidden="true"
          className="size-3.5 shrink-0 transition-transform duration-200 group-open/pages:rotate-90"
        />
        Show chosen pages
      </summary>
      <div className="mt-1.5 flex flex-col gap-2">
        {groups
          .filter((g) => g.found > 0)
          .map((g) => (
            <div key={g.name}>
              <p className="font-semibold text-foreground">
                {GROUP_LABEL[g.name] ?? g.name}{' '}
                <span className="font-normal text-muted-foreground">
                  · {g.picked.length} chosen
                  {g.skipped > 0 ? `, ${g.skipped} skipped` : ''} of {g.found}
                </span>
              </p>
              <ul className="ml-3 list-disc break-all text-muted-foreground">
                {g.picked.map((u) => (
                  <li key={u}>{pathOf(u)}</li>
                ))}
              </ul>
            </div>
          ))}
      </div>
    </details>
  )
}

/** How many read-page rows stay on screen. Older rows slide up and out. */
const PAGE_QUEUE = 5

function Pages({ steps }: { steps: Map<string, TraceEvent> }) {
  const pages = [...steps.values()].filter((e) => e.id.startsWith('page:'))
  const frameRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const signature = pages.map((p) => `${p.id}\0${p.status}\0${p.ms ?? ''}`).join('\n')

  useLayoutEffect(() => {
    const frame = frameRef.current
    const list = listRef.current
    if (!frame || !list) return

    const placeQueue = () => {
      const items = [...list.children] as HTMLElement[]
      if (items.length === 0 || signature.length === 0) return
      // First-seen order, so the window is the newest PAGE_QUEUE rows (FIFO).
      // Rects stay correct after the list is translated, because the shift cancels out.
      const start = Math.max(0, items.length - PAGE_QUEUE)
      const first = items[start]
      if (!first) return
      const top = Math.max(0, first.getBoundingClientRect().top - list.getBoundingClientRect().top)
      const height = list.scrollHeight - top
      // A closed ancestor lays out at 0. ResizeObserver fits the window once it opens.
      if (height <= 0) return
      const nextHeight = `${height}px`
      const nextTransform = top > 0 ? `translateY(-${top}px)` : ''
      if (frame.style.height !== nextHeight) frame.style.height = nextHeight
      if (list.style.transform !== nextTransform) list.style.transform = nextTransform
    }

    placeQueue()
    const observer = new ResizeObserver(placeQueue)
    observer.observe(list)
    return () => observer.disconnect()
  }, [signature])

  if (pages.length === 0) return null
  return (
    <div
      ref={frameRef}
      data-page-queue={PAGE_QUEUE}
      className="mt-1.5 overflow-hidden motion-safe:transition-[height] motion-safe:duration-300 motion-safe:ease-out"
    >
      <ul
        ref={listRef}
        aria-label="Latest pages read"
        className="relative flex flex-col gap-1 text-[12px] motion-safe:transition-transform motion-safe:duration-300 motion-safe:ease-out"
      >
        {pages.map((p, i) => (
          <li
            key={p.id}
            aria-hidden={i < pages.length - PAGE_QUEUE ? true : undefined}
            className="flex items-start gap-1.5"
          >
            <Icon status={p.status} />
            <span className="min-w-0 flex-1 break-all text-muted-foreground">
              {pathOf(text(p.detail.url) ?? p.label)}
            </span>
            <span className="shrink-0 text-muted-foreground tabular-nums">{duration(p.ms)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Steps({ audit, busy }: { audit: Audit; busy: boolean }) {
  const steps = foldTrace(audit.trace)
  const rows: ReactNode[] = []
  for (const { id, label } of STEPS) {
    const e = steps.get(id)
    if (id === 'usage') {
      // Only once the audit has spent something; no "waiting" row for it while it runs.
      if (e) rows.push(<UsageStep key="usage" event={e} />)
      continue
    }
    if (!e && !busy) continue
    const note = e ? summary(id, e, steps) : null
    rows.push(
      <li key={id} className="flex items-start gap-2.5 py-1.5">
        <Icon status={e?.status ?? 'pending'} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'flex-1 text-[14px] font-semibold',
                !e && 'font-normal text-muted-foreground',
              )}
            >
              {label}
            </span>
            <span className="shrink-0 text-[12px] text-muted-foreground tabular-nums">
              {duration(e?.ms ?? null)}
            </span>
          </div>
          {note ? (
            <p
              className={cn(
                'text-[13px] text-muted-foreground',
                e?.status === 'failed' && 'text-destructive',
              )}
            >
              {note}
            </p>
          ) : null}
          {e && id === 'pick' && e.status === 'done' ? <PickGroups event={e} /> : null}
          {id === 'scrape' ? <Pages steps={steps} /> : null}
        </div>
      </li>,
    )
  }
  const final = steps.get('final')
  if (final) {
    const outcome = text(final.detail.outcome)
    rows.push(
      <li key="final" className="flex items-start gap-2.5 py-1.5">
        <Icon status={final.status} />
        <span className="flex-1 text-[14px] font-semibold">
          {outcome === 'failed'
            ? 'Audit failed'
            : outcome === 'partial'
              ? 'Audit finished with some parts missing'
              : 'Audit finished'}
        </span>
        <span className="shrink-0 text-[12px] text-muted-foreground tabular-nums">
          {duration(runTime(audit))}
        </span>
      </li>,
    )
  }
  return <ol className="divide-y divide-border/60">{rows}</ol>
}

function runTime(audit: Audit): number | null {
  if (!audit.finishedAt) return null
  const ms = Date.parse(audit.finishedAt) - Date.parse(audit.createdAt)
  return Number.isFinite(ms) && ms >= 0 ? ms : null
}

/** Live step list while the audit runs; a collapsed "How this audit ran" once it is over. */
export function AuditProgress({ audit, tab }: { audit: Audit; tab?: string }) {
  const busy = audit.status === 'queued' || audit.status === 'running'
  const [open, setOpen] = useState(audit.status === 'failed')
  const seenTab = useRef(tab)

  useEffect(() => {
    if (seenTab.current === tab) return
    seenTab.current = tab
    setOpen(false)
    console.info('[audit-progress] collapse', { tab })
  }, [tab])

  if (!busy && audit.trace.length === 0) return null
  // Research has its own "How this check ran". The audit trace only belongs on the other tabs.
  if (!busy && tab === 'research') return null
  if (busy) {
    return (
      <section
        aria-label="Audit progress"
        className="mb-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5"
      >
        <SectionTitle>Audit progress</SectionTitle>
        <Steps audit={audit} busy />
      </section>
    )
  }
  return (
    <details
      aria-label="Audit progress"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="audit-trace group mb-3 rounded-lg border border-border bg-card px-3 py-2 text-card-foreground"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] font-semibold [&::-webkit-details-marker]:hidden">
        <ChevronRightIcon
          aria-hidden="true"
          className="size-4 shrink-0 transition-transform duration-200 group-open:rotate-90"
        />
        How this audit ran
      </summary>
      <div className="mt-1.5">
        <Steps audit={audit} busy={false} />
      </div>
    </details>
  )
}
