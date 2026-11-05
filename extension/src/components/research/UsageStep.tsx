import { ChevronRightIcon, CircleCheckIcon } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import type { TraceEvent } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const count = (n: number) => n.toLocaleString('en-US')

function money(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.0001) return '<$0.0001'
  return `$${usd.toFixed(4)}`
}

function seconds(ms: number | null): string {
  if (ms == null) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

interface Line {
  kind: string
  label: string
  calls: number
  tokens: number
  costUsd: number
  note: string
}

/** One source of spend. Detail keys arrive camelCased from the API client. */
function lineOf(raw: unknown): Line | null {
  if (typeof raw !== 'object' || raw === null) return null
  const x = raw as Record<string, unknown>
  if (typeof x.label !== 'string') return null
  return {
    kind: typeof x.kind === 'string' ? x.kind : 'ai',
    label: x.label,
    calls: num(x.calls),
    tokens: num(x.tokens),
    costUsd: num(x.costUsd),
    note: typeof x.note === 'string' ? x.note : '',
  }
}

function Breakdown({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex cursor-pointer items-center gap-1 text-left text-[12px] text-primary"
      >
        <ChevronRightIcon
          aria-hidden="true"
          className={cn(
            'size-3.5 shrink-0 transition-transform duration-200 ease-out',
            open && 'rotate-90',
          )}
        />
        Show breakdown
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

/**
 * The audit's "Cost and tokens" step, shown just before the last step. Input tokens are the
 * text sent to the AI (the pages it reads); output tokens are what it writes. The dollar total
 * is what OpenRouter reports for the AI calls. Firecrawl and Apify bill in credits, so they
 * appear as call counts and never inside the dollar total.
 */
export function UsageStep({ event }: { event: TraceEvent }) {
  const d = event.detail
  const lines = (Array.isArray(d.lines) ? d.lines : [])
    .map(lineOf)
    .filter((l): l is Line => l !== null)
  const ai = lines.filter((l) => l.kind === 'ai')
  const other = lines.filter((l) => l.kind !== 'ai')
  const tokens = num(d.tokens)
  const calls = num(d.calls)
  const paid = other.map((l) => `${l.label} ${l.calls} ${l.calls === 1 ? 'call' : 'calls'}`)
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <CircleCheckIcon aria-label="done" className="mt-0.5 size-4 shrink-0 text-success" />
      <div className="min-w-0 flex-1">
        <span className="text-[14px] font-semibold">{event.label}</span>
        {ai.length > 0 ? (
          <>
            <p className="text-[13px] tabular-nums">
              <span className="font-semibold">{money(num(d.costUsd))}</span> total · {count(tokens)}{' '}
              tokens
            </p>
            <p className="text-[12px] text-muted-foreground tabular-nums">
              {count(num(d.promptTokens))} input · {count(num(d.completionTokens))} output · {calls}{' '}
              AI {calls === 1 ? 'call' : 'calls'}
              {event.ms != null ? ` · ${seconds(event.ms)} in all` : ''}
            </p>
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground tabular-nums">
            No AI calls{event.ms != null ? ` · ${seconds(event.ms)} in all` : ''}
          </p>
        )}
        {paid.length > 0 ? (
          <p className="text-[12px] text-muted-foreground tabular-nums">{paid.join(' · ')}</p>
        ) : null}
        {lines.length > 0 ? (
          <Breakdown>
            <table className="w-full text-[12px] tabular-nums">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="font-medium">Source</th>
                  <th className="text-right font-medium">Tokens</th>
                  <th className="text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.label} className="border-t border-border/60">
                    <td className="py-0.5">
                      {l.label}
                      {l.note ? (
                        <span className="block text-muted-foreground">{l.note}</span>
                      ) : null}
                    </td>
                    <td className="text-right">
                      {l.kind === 'ai' ? count(l.tokens) : `${l.calls} calls`}
                    </td>
                    <td className="text-right">{l.kind === 'ai' ? money(l.costUsd) : 'credits'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {other.length > 0 ? (
              <p className="mt-1 text-[12px] text-muted-foreground">
                The dollar total counts AI calls only. Firecrawl and Apify bill in credits.
              </p>
            ) : null}
          </Breakdown>
        ) : null}
      </div>
    </li>
  )
}
