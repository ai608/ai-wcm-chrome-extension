import type { ReactNode } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import type { Audit, CheckStatus, Grade, SectionKey } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

export const SECTION_LABEL: Record<string, string> = {
  overview: 'Overview',
  business: 'Business',
  on_page: 'On-Page',
  schema: 'Schema',
  site: 'Site',
  convert: 'Convert',
  research: 'Research',
}

export function gradeClass(g: Grade | string): string {
  if (g === 'A' || g === 'B') return 'bg-success text-success-foreground'
  if (g === 'C') return 'bg-accent-wcm text-white'
  return 'bg-destructive text-white'
}

export function gradeText(g: Grade | string): string {
  if (g === 'A' || g === 'B') return 'text-success border-success/40'
  if (g === 'C') return 'text-accent-wcm border-accent-wcm/40'
  return 'text-destructive border-destructive/40'
}

const DOT: Record<CheckStatus, string> = {
  ok: 'bg-success',
  warn: 'bg-accent-wcm',
  fail: 'bg-destructive',
  info: 'bg-muted-foreground',
}

export function StatusDot({ status }: { status: CheckStatus }) {
  return (
    <span
      role="img"
      aria-label={status}
      className={cn('mt-1.5 inline-block size-2 shrink-0 rounded-full', DOT[status])}
    />
  )
}

export function StatBox({
  label,
  value,
  tone,
}: {
  label: string
  value: ReactNode
  tone?: 'bad' | 'good'
}) {
  return (
    <div className="flex-1 rounded-lg bg-muted px-3 py-2.5">
      <p
        className={cn(
          'text-lg font-semibold leading-tight',
          tone === 'bad' && 'text-destructive',
          tone === 'good' && 'text-success',
        )}
      >
        {value}
      </p>
      <p className="text-[12px] text-muted-foreground">{label}</p>
    </div>
  )
}

export function Chip({
  children,
  tone = 'default',
}: {
  children: ReactNode
  tone?: 'default' | 'good' | 'bad' | 'warn'
}) {
  return (
    <span
      className={cn(
        'inline-block rounded-full border px-2 py-0.5 text-[12px]',
        tone === 'default' && 'border-border bg-muted text-foreground',
        tone === 'good' && 'border-success/40 text-success',
        tone === 'bad' && 'border-destructive/40 text-destructive',
        tone === 'warn' && 'border-accent-wcm/40 text-accent-wcm',
      )}
    >
      {children}
    </span>
  )
}

export function Row({
  label,
  children,
  status,
}: {
  label: string
  children?: ReactNode
  status?: CheckStatus
}) {
  return (
    <div className="flex items-start gap-2.5 border-b border-border/70 py-2.5 text-[14px] last:border-b-0">
      {/* Rows without a status keep the dot's slot, so labels and values line up down the list. */}
      {status ? (
        <StatusDot status={status} />
      ) : (
        <span aria-hidden="true" className="size-2 shrink-0" />
      )}
      <span className="w-32 shrink-0 font-semibold text-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-words text-muted-foreground">{children}</span>
    </div>
  )
}

/** The one style for every section heading in the panel (1rem, semibold, full ink). */
export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h3 className={cn('py-0.5 text-base font-semibold leading-6 text-foreground', className)}>
      {children}
    </h3>
  )
}

export function Block({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section>
      {title ? <SectionTitle className="mb-2">{title}</SectionTitle> : null}
      {children}
    </section>
  )
}

export function InfoNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg bg-primary/10 px-3 py-2.5 text-[13px] leading-relaxed text-primary">
      {children}
    </p>
  )
}

export function SubTabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T
  onChange: (v: T) => void
  items: { value: T; label: string }[]
}) {
  return (
    <div className="flex gap-2 overflow-x-auto border-b border-border pb-3">
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          aria-pressed={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            'shrink-0 whitespace-nowrap rounded-full border border-border bg-muted px-3.5 py-1.5 text-[13px] font-semibold text-foreground/70',
            value === it.value && 'border-primary bg-primary font-semibold text-white',
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

export function FilterChips<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T
  onChange: (v: T) => void
  items: { value: T; label: string }[]
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          aria-pressed={value === it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            'rounded-full border border-border px-2.5 py-0.5 text-[12px]',
            value === it.value && 'border-primary bg-primary font-semibold text-white',
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

export function ExtLink({ href, children }: { href: string; children: ReactNode }) {
  let safe = '#'
  try {
    const u = new URL(href)
    if (u.protocol === 'http:' || u.protocol === 'https:') safe = u.toString()
  } catch {
    // leave '#'
  }
  return (
    <a
      href={safe}
      target="_blank"
      rel="noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {children}
    </a>
  )
}

/** Renders skeleton / failed / skipped states for a section, children when ready. */
export function SectionGate({
  audit,
  section,
  children,
}: {
  audit: Audit
  section: SectionKey
  children: ReactNode
}) {
  const state = audit.sectionState[section]
  if (state === 'failed') {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {SECTION_LABEL[section]} couldn’t be loaded{audit.error ? `: ${audit.error}` : '.'}
        </AlertDescription>
      </Alert>
    )
  }
  if (state === 'skipped') {
    return <p className="text-[13px] text-muted-foreground">Not available for this site.</p>
  }
  if (state !== 'ready') {
    return (
      <div className="flex flex-col gap-2" role="status" aria-label={`Loading ${section}`}>
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }
  return <>{children}</>
}

export function host(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}
