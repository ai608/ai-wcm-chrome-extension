import { ArrowUpRightIcon, CheckIcon, CopyIcon, ImageIcon, SearchIcon } from 'lucide-react'
import { useState } from 'react'
import { Block, FilterChips, Row, SectionTitle, SubTabs } from '@/components/research/shared'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'
import type { Audit, OnPageSection } from '@/lib/api/research-types'
import { downloadCsv, toCsv } from '@/lib/csv'
import { cn } from '@/lib/utils'
import { usePanelStore } from '@/stores/panel-store'

type Sub = 'essentials' | 'headings' | 'links' | 'images' | 'speed'
const SUBS: { value: Sub; label: string }[] = [
  { value: 'essentials', label: 'Essentials' },
  { value: 'headings', label: 'Headings' },
  { value: 'links', label: 'Links' },
  { value: 'images', label: 'Images' },
  { value: 'speed', label: 'Speed' },
]

type Heading = OnPageSection['headings']['outline'][number]

// Level labels are plain coloured text: the H1 stands out in red, the rest share the brand blue.
const LEVEL_LABEL: Record<number, string> = { 1: 'text-destructive' }
const LEVEL_TEXT: Record<number, string> = {
  1: 'text-[15px] font-semibold text-foreground',
  2: 'text-[14px] font-medium text-foreground',
  3: 'text-[13px] text-foreground/85',
}

/** Levels that jump more than one step down from the heading before (H2 straight to H4). */
export function skippedLevels(outline: Heading[]): Set<number> {
  const skipped = new Set<number>()
  outline.forEach((o, i) => {
    const prev = outline[i - 1]
    if (prev && o.level > prev.level + 1) skipped.add(i)
  })
  return skipped
}

function Headings({ h }: { h: OnPageSection['headings'] }) {
  const [copied, setCopied] = useState(false)
  const h1 =
    h.h1Count === 1 ? 'Exactly one H1' : h.h1Count === 0 ? 'No H1 on this page' : `${h.h1Count} H1s`
  const text = h.outline.map((o) => `${'  '.repeat(o.level - 1)}H${o.level} ${o.text}`).join('\n')
  const skipped = skippedLevels(h.outline)
  const counts = [1, 2, 3, 4, 5, 6]
    .map((l) => [l, h.outline.filter((o) => o.level === l).length] as const)
    .filter(([, n]) => n > 0)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 rounded-lg bg-muted/50 px-3 py-2.5">
        <Row label="H1 check" status={h.h1Count === 1 ? 'ok' : 'fail'}>
          {h1}
        </Row>
        <Row label="Structure" status={skipped.size ? 'warn' : 'ok'}>
          {skipped.size === 0
            ? 'No skipped levels'
            : skipped.size === 1
              ? '1 heading skips a level'
              : `${skipped.size} headings skip a level`}
        </Row>
        <p className="text-[12px] tabular-nums text-muted-foreground">
          {h.outline.length} headings
          {counts.length ? ` · ${counts.map(([l, n]) => `${n} H${l}`).join(' · ')}` : ''}
        </p>
      </div>
      <div className="flex items-center justify-between gap-2">
        <SectionTitle>Outline ({h.outline.length})</SectionTitle>
        <Button
          variant="outline"
          size="xs"
          disabled={!h.outline.length}
          onClick={() =>
            navigator.clipboard
              .writeText(text)
              .then(() => {
                setCopied(true)
                toast('Copied')
                setTimeout(() => setCopied(false), 1500)
              })
              .catch(() => toast('Couldn’t copy'))
          }
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? 'Copied' : 'Copy outline'}
        </Button>
      </div>
      {h.outline.length ? (
        <ol aria-label="Heading outline" className="flex flex-col gap-0.5">
          {h.outline.map((o, i) => (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: static outline, order is identity
              key={i}
              style={{ marginLeft: (o.level - 1) * 14 }}
              className={cn(
                'flex min-w-0 items-baseline gap-2 rounded-md py-1 pr-1.5 pl-2 hover:bg-muted/60',
                o.level > 1 && 'border-l-2 border-border',
              )}
            >
              <span
                className={cn(
                  'w-6 shrink-0 text-[11px] font-bold tabular-nums',
                  LEVEL_LABEL[o.level] ?? 'text-primary',
                )}
              >
                H{o.level}
              </span>
              <span
                className={cn(
                  'min-w-0 break-words',
                  LEVEL_TEXT[o.level] ?? 'text-[13px] text-muted-foreground',
                )}
              >
                {o.text || <em className="text-muted-foreground">Empty heading</em>}
              </span>
              {skipped.has(i) ? (
                <span className="ml-auto shrink-0 rounded-full bg-accent-wcm/15 px-2 py-px text-[11px] font-semibold text-accent-wcm">
                  Skips a level
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[13px] text-muted-foreground">
          This page has no headings.
        </p>
      )}
    </div>
  )
}

type LinkItem = OnPageSection['links']['items'][number]
type LinkFilter = 'all' | 'internal' | 'external' | 'nofollow'
const LINK_PAGE = 50
// Peer figures share one frame split by 1px hairlines (the gap shows the border colour).
const HAIRLINE_GRID =
  'grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border min-[420px]:grid-cols-4'
const LINK_FILTERS: [LinkFilter, string][] = [
  ['all', 'All'],
  ['internal', 'Internal'],
  ['external', 'External'],
  ['nofollow', 'Nofollow'],
]
const LINK_EMPTY: Record<LinkFilter, string> = {
  all: 'No links found on this page.',
  internal: 'No links to other pages on this site.',
  external: 'No links to other websites.',
  nofollow: 'No nofollow links on this page.',
}

/** Header and footer menus repeat the same link; fold repeats into one row with a count.
 *  The fold key is also the React key, so rows stay unique when the list is filtered. */
export function foldLinks(items: LinkItem[]): (LinkItem & { key: string; count: number })[] {
  const rows = new Map<string, LinkItem & { key: string; count: number }>()
  for (const i of items) {
    const key = `${i.kind}|${i.nofollow}|${i.href}|${i.text}`
    const row = rows.get(key)
    if (row) row.count++
    else rows.set(key, { ...i, key, count: 1 })
  }
  return [...rows.values()]
}

function linkWhere(i: LinkItem): string {
  try {
    const u = new URL(i.href)
    return i.kind === 'internal' ? `${u.pathname}${u.search}` || '/' : u.host
  } catch {
    return i.href
  }
}

function safeHref(href: string): string | undefined {
  try {
    const u = new URL(href)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : undefined
  } catch {
    return undefined
  }
}

function Links({ audit, l }: { audit: Audit; l: OnPageSection['links'] }) {
  const [f, setF] = useState<LinkFilter>('all')
  const [q, setQ] = useState('')
  const [showAll, setShowAll] = useState(false)
  const counts: Record<LinkFilter, number> = {
    all: l.items.length,
    internal: l.items.filter((i) => i.kind === 'internal').length,
    external: l.items.filter((i) => i.kind === 'external').length,
    nofollow: l.items.filter((i) => i.nofollow).length,
  }
  const needle = q.trim().toLowerCase()
  const rows = foldLinks(l.items).filter(
    (i) =>
      (f === 'all' || (f === 'nofollow' ? i.nofollow : i.kind === f)) &&
      (!needle || `${i.text} ${i.href}`.toLowerCase().includes(needle)),
  )
  const shown = showAll ? rows : rows.slice(0, LINK_PAGE)
  return (
    <div className="flex flex-col gap-3">
      {/* The counts are the filters: one container split by hairlines, the active one underlined. */}
      <div className={HAIRLINE_GRID}>
        {LINK_FILTERS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={f === key}
            onClick={() => {
              setF(key)
              setShowAll(false)
            }}
            className={cn(
              'flex flex-col items-start border-b-2 bg-background px-3 py-2 text-left outline-none focus-visible:bg-muted',
              f === key ? 'border-b-primary' : 'border-b-transparent hover:bg-muted/50',
            )}
          >
            <span
              className={cn(
                'text-[12px]',
                f === key ? 'font-semibold text-foreground' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
            <span
              className={cn(
                'text-lg leading-tight tabular-nums text-foreground',
                f === key ? 'font-semibold' : 'font-normal',
              )}
            >
              {counts[key]}
            </span>
          </button>
        ))}
      </div>
      <div className="relative">
        <SearchIcon
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="search"
          aria-label="Search links"
          placeholder="Search link text or URL"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setShowAll(false)
          }}
          className="pl-8 text-[13px] md:text-[13px]"
        />
      </div>
      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-[13px] text-muted-foreground">
          {needle ? 'No links match.' : LINK_EMPTY[f]}
        </p>
      ) : (
        <ul
          aria-label="Links"
          className="divide-y divide-border overflow-hidden rounded-lg border border-border"
        >
          {shown.map((i) => {
            const href = safeHref(i.href)
            return (
              <li key={i.key}>
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={i.href}
                  className="group flex min-h-11 items-center gap-2 px-3 py-1.5 outline-none focus-visible:bg-muted"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-foreground group-hover:text-primary">
                      {i.text || (
                        <span className="font-normal italic text-muted-foreground">
                          No anchor text
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-1 text-[12px] text-muted-foreground">
                      {i.kind === 'external' ? (
                        <ArrowUpRightIcon aria-label="External" className="size-3 shrink-0" />
                      ) : null}
                      <span className="truncate">{linkWhere(i)}</span>
                    </span>
                  </span>
                  {i.nofollow ? (
                    <span className="shrink-0 rounded border border-accent-wcm/40 px-1.5 text-[11px] font-medium text-accent-wcm">
                      nofollow
                    </span>
                  ) : null}
                  {i.count > 1 ? (
                    <span
                      className="shrink-0 rounded bg-muted px-1.5 text-[11px] font-medium tabular-nums text-muted-foreground"
                      title={`Appears ${i.count} times on the page`}
                    >
                      ×{i.count}
                    </span>
                  ) : null}
                </a>
              </li>
            )
          })}
        </ul>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        {rows.length > LINK_PAGE && !showAll ? (
          <Button variant="ghost" size="sm" onClick={() => setShowAll(true)}>
            Show all {rows.length}
          </Button>
        ) : (
          <span className="text-[12px] text-muted-foreground">
            {rows.length} {rows.length === 1 ? 'link' : 'links'}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={rows.length === 0}
          onClick={() =>
            downloadCsv(
              audit.domain,
              'links',
              toCsv(
                rows.map((i) => ({
                  href: i.href,
                  text: i.text,
                  kind: i.kind,
                  nofollow: i.nofollow,
                  times: i.count,
                })),
              ),
            )
          }
        >
          Export {rows.length} to CSV
        </Button>
      </div>
    </div>
  )
}

// Images embedded in the page (data: URIs) carry the whole file in `src`; name them instead.
export function imageName(src: string): string {
  if (src.startsWith('data:')) {
    const kind = /^data:image\/([a-z0-9.+-]+)/i.exec(src)?.[1]?.replace('svg+xml', 'svg')
    return `Embedded ${kind ? kind.toUpperCase() : ''} image`.replace('  ', ' ')
  }
  const file = src.split(/[?#]/)[0]?.split('/').pop() || src
  try {
    return decodeURIComponent(file)
  } catch {
    return file
  }
}

const IMAGE_PAGE = 50

// 1×1 images are tracking pixels: they are never loaded here, so previewing a report does not
// ping the clinic's ad networks from the viewer's browser.
const isPixel = (i: { width: number | null; height: number | null }) =>
  i.width != null && i.height != null && i.width <= 2 && i.height <= 2

function Thumb({ src, pixel }: { src: string; pixel: boolean }) {
  const [broken, setBroken] = useState(false)
  const loadable = !pixel && !broken && /^https?:\/\//i.test(src)
  return (
    <span className="grid size-11 shrink-0 place-items-center overflow-hidden rounded-md bg-muted text-muted-foreground">
      {loadable ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          className="size-full object-contain"
          onError={() => setBroken(true)}
        />
      ) : (
        <ImageIcon className="size-4" aria-hidden="true" />
      )}
    </span>
  )
}

function ImageStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'bad' | 'good'
}) {
  return (
    <div className="rounded-lg border border-border px-2 py-3 text-center">
      <p
        className={cn(
          'text-2xl font-semibold leading-none tabular-nums',
          tone === 'bad' && 'text-destructive',
          tone === 'good' && 'text-success',
        )}
      >
        {value}
      </p>
      <p className="mt-1.5 text-[12px] text-muted-foreground">{label}</p>
    </div>
  )
}

function Images({ audit, im }: { audit: Audit; im: OnPageSection['images'] }) {
  const [f, setF] = useState<'all' | 'missing'>('all')
  const [all, setAll] = useState(false)
  const items = im.items.filter((i) => (f === 'missing' ? !i.alt : true))
  const shown = all ? items : items.slice(0, IMAGE_PAGE)
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        <ImageStat label="Images" value={im.total} />
        <ImageStat
          label="Missing alt"
          value={im.missingAlt}
          tone={im.missingAlt ? 'bad' : 'good'}
        />
        <ImageStat label="Lazy loaded" value={im.lazy} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilterChips
          value={f}
          onChange={(v) => {
            setF(v)
            setAll(false)
          }}
          items={[
            { value: 'all', label: `All ${im.items.length}` },
            { value: 'missing', label: `Missing alt ${im.items.filter((i) => !i.alt).length}` },
          ]}
        />
        <Button
          variant="outline"
          size="xs"
          disabled={!items.length}
          onClick={() =>
            downloadCsv(
              audit.domain,
              'images',
              toCsv(
                items.map((i) => ({
                  src: i.src.startsWith('data:') ? imageName(i.src) : i.src,
                  alt: i.alt,
                  width: i.width,
                  height: i.height,
                })),
              ),
            )
          }
        >
          Export {items.length} to CSV
        </Button>
      </div>
      {items.length ? (
        <ul aria-label="Images" className="flex flex-col divide-y divide-border/70">
          {shown.map((i, idx) => {
            const pixel = isPixel(i)
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: one image can appear twice; rows hold no state
              <li key={`${idx}-${i.src}`} className="flex items-center gap-3 py-2.5">
                <Thumb src={i.src} pixel={pixel} />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-2 text-[14px] leading-5">
                    {i.alt ? (
                      <span className="min-w-0 break-words font-medium text-foreground">
                        {i.alt}
                      </span>
                    ) : (
                      <span className="font-semibold text-destructive">Missing alt text</span>
                    )}
                    {pixel ? (
                      <span className="rounded bg-muted px-1.5 py-px text-[11px] font-medium text-muted-foreground">
                        Tracking pixel
                      </span>
                    ) : null}
                  </p>
                  <p
                    className="truncate text-[12px] text-muted-foreground"
                    title={i.src.startsWith('data:') ? undefined : i.src}
                  >
                    {imageName(i.src)}
                    {i.width && i.height ? ` · ${i.width}×${i.height}` : ''}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[13px] text-muted-foreground">
          {f === 'missing' ? 'Every image has alt text.' : 'No images found on this page.'}
        </p>
      )}
      {items.length > shown.length ? (
        <Button variant="outline" size="sm" onClick={() => setAll(true)}>
          Show all {items.length}
        </Button>
      ) : null}
    </div>
  )
}

type Band = 'good' | 'average' | 'poor'
// Google's PageSpeed bands: scores 90+ good, 50–89 needs work; LCP 2.5 s / 4 s; CLS 0.1 / 0.25.
export const scoreBand = (v: number): Band => (v >= 90 ? 'good' : v >= 50 ? 'average' : 'poor')
export const lcpBand = (ms: number): Band => (ms <= 2500 ? 'good' : ms <= 4000 ? 'average' : 'poor')
export const clsBand = (v: number): Band => (v <= 0.1 ? 'good' : v <= 0.25 ? 'average' : 'poor')

const BAND_LABEL: Record<Band, string> = { good: 'Good', average: 'Needs work', poor: 'Poor' }
const BAND_TEXT: Record<Band, string> = {
  good: 'text-success',
  average: 'text-accent-wcm',
  poor: 'text-destructive',
}
const BAND_PILL: Record<Band, string> = {
  good: 'border-success/40 bg-success/10 text-success',
  average: 'border-accent-wcm/40 bg-accent-wcm/10 text-accent-wcm',
  poor: 'border-destructive/40 bg-destructive/10 text-destructive',
}
const BAND_DOT: Record<Band, string> = {
  good: 'bg-success',
  average: 'bg-accent-wcm',
  poor: 'bg-destructive',
}
const BAND_RANGE: Record<Band, string> = { poor: '0–49', average: '50–89', good: '90–100' }
const CLS_SAY: Record<Band, string> = {
  good: 'The page barely moves while it loads.',
  average: 'Some content jumps while the page loads.',
  poor: 'Content jumps around a lot while the page loads.',
}

function ScoreRing({ label, value }: { label: string; value: number | null }) {
  const band = value == null ? null : scoreBand(value)
  const r = 22
  const c = 2 * Math.PI * r
  return (
    <div
      role="img"
      aria-label={value == null ? `${label} not measured` : `${label} ${value}, ${band}`}
      className="flex flex-col items-center gap-1.5 bg-background px-2 py-3"
    >
      <svg viewBox="0 0 56 56" className="size-14" aria-hidden="true">
        <circle cx="28" cy="28" r={r} fill="none" strokeWidth="4" className="stroke-muted" />
        {value != null ? (
          <circle
            cx="28"
            cy="28"
            r={r}
            fill="none"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={`${(c * value) / 100} ${c}`}
            transform="rotate(-90 28 28)"
            className={cn('stroke-current', band && BAND_TEXT[band])}
          />
        ) : null}
        <text
          x="28"
          y="28"
          textAnchor="middle"
          dominantBaseline="central"
          className={cn(
            'fill-current text-[15px] font-semibold',
            band ? BAND_TEXT[band] : 'text-muted-foreground',
          )}
        >
          {value ?? '–'}
        </text>
      </svg>
      <span className="text-center text-[12px] leading-tight font-medium text-foreground">
        {label}
      </span>
    </div>
  )
}

function Vital({
  name,
  value,
  band,
  say,
  scale,
}: {
  name: string
  value: string | null
  band: Band | null
  say: string | null
  scale: string
}) {
  return (
    <li className="flex flex-col gap-0.5 py-2.5">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[13px] font-semibold text-foreground">{name}</span>
        <span className="text-[13px] font-semibold tabular-nums text-foreground">
          {value ?? '–'}
        </span>
        {band ? (
          <span
            className={cn(
              'rounded-full border px-2 py-0.5 text-[11px] font-semibold',
              BAND_PILL[band],
            )}
          >
            {BAND_LABEL[band]}
          </span>
        ) : (
          <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
            Not measured
          </span>
        )}
      </div>
      {say ? <p className="text-[13px] text-muted-foreground">{say}</p> : null}
      <p className="text-[12px] text-muted-foreground">{scale}</p>
    </li>
  )
}

type Strategy = 'mobile' | 'desktop'
type Pagespeed = NonNullable<OnPageSection['pagespeed']>
type Scores = NonNullable<Pagespeed['desktop']>

/** The audit stores mobile as flat fields and desktop as a block (absent on older audits). */
function scoresFor(p: Pagespeed, strategy: Strategy): Scores | null {
  if (strategy === 'desktop') return p.desktop ?? null
  return { ...p, performance: p.mobilePerformance }
}

function StrategySwitch({ value, onChange }: { value: Strategy; onChange: (v: Strategy) => void }) {
  return (
    <div className="inline-flex gap-0.5 rounded-full border border-border bg-muted p-0.5">
      {(['mobile', 'desktop'] as const).map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={value === s}
          onClick={() => onChange(s)}
          className={cn(
            'rounded-full px-2.5 py-0.5 text-[12px] font-semibold text-foreground/70 outline-none focus-visible:outline-2 focus-visible:outline-ring',
            value === s && 'bg-primary text-white',
          )}
        >
          {s === 'mobile' ? 'Mobile' : 'Desktop'}
        </button>
      ))}
    </div>
  )
}

function Speed({ audit, p }: { audit: Audit; p: OnPageSection['pagespeed'] }) {
  const [strategy, setStrategy] = useState<Strategy>('mobile')
  const base = `https://pagespeed.web.dev/analysis?url=${encodeURIComponent(audit.url)}`
  if (!p)
    return (
      <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-border px-4 py-5">
        <p className="text-[13px] font-semibold text-foreground">
          No PageSpeed data for this audit.
        </p>
        <p className="text-[13px] text-muted-foreground">
          The speed check didn’t return results. Re-run the audit, or check the site on Google’s
          PageSpeed page.
        </p>
        <a
          href={base}
          target="_blank"
          rel="noreferrer"
          className={buttonVariants({ variant: 'outline', size: 'sm' })}
        >
          Run it on PageSpeed <ArrowUpRightIcon aria-hidden="true" />
        </a>
      </div>
    )
  const report = `${base}&form_factor=${strategy}`
  const s = scoresFor(p, strategy)
  const lcp = s?.lcpMs == null ? null : lcpBand(s.lcpMs)
  const cls = s?.cls == null ? null : clsBand(s.cls)
  const seconds = s?.lcpMs == null ? null : (s.lcpMs / 1000).toFixed(1)
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <SectionTitle>Lighthouse scores</SectionTitle>
          <StrategySwitch value={strategy} onChange={setStrategy} />
        </div>
        {s ? (
          <div className={HAIRLINE_GRID}>
            <ScoreRing label="Performance" value={s.performance} />
            <ScoreRing label="SEO" value={s.seo} />
            <ScoreRing label="Accessibility" value={s.accessibility} />
            <ScoreRing label="Best practices" value={s.bestPractices} />
          </div>
        ) : (
          <p className="text-[13px] text-muted-foreground">
            Desktop wasn’t measured for this audit. Re-run the audit to get it.
          </p>
        )}
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
          {(['poor', 'average', 'good'] as const).map((b) => (
            <span key={b} className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span aria-hidden="true" className={cn('size-2 rounded-full', BAND_DOT[b])} />
              {BAND_RANGE[b]} {BAND_LABEL[b].toLowerCase()}
            </span>
          ))}
        </p>
      </section>
      {s ? (
        <section className="flex flex-col">
          <SectionTitle>Core Web Vitals</SectionTitle>
          <ul className="divide-y divide-border">
            <Vital
              name="Largest Contentful Paint"
              value={seconds == null ? null : `${seconds} s`}
              band={lcp}
              say={seconds == null ? null : `Main content shows in ${seconds} s.`}
              scale="Good ≤ 2.5 s · Poor over 4 s"
            />
            <Vital
              name="Cumulative Layout Shift"
              value={s.cls == null ? null : String(s.cls)}
              band={cls}
              say={cls ? CLS_SAY[cls] : null}
              scale="Good ≤ 0.1 · Poor over 0.25"
            />
          </ul>
        </section>
      ) : null}
      <a
        href={report}
        target="_blank"
        rel="noreferrer"
        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'self-start')}
      >
        Open full report in PageSpeed <ArrowUpRightIcon aria-hidden="true" />
      </a>
    </div>
  )
}

export function OnPageTab({ audit, onPage }: { audit: Audit; onPage: OnPageSection }) {
  const sub = (usePanelStore((s) => s.researchSubTab.on_page) as Sub | undefined) ?? 'essentials'
  const setSub = usePanelStore((s) => s.setResearchSubTab)
  return (
    <div className="flex flex-col gap-3">
      <SubTabs value={sub} onChange={(v) => setSub('on_page', v)} items={SUBS} />
      {sub === 'essentials' ? (
        <Block>
          {onPage.essentials.map((e) => (
            <Row key={e.key} label={e.label} status={e.status}>
              <span className={e.status === 'info' ? 'font-semibold text-foreground' : ''}>
                {e.value}
              </span>
              {e.note ? (
                <span
                  className={`ml-2 rounded px-1.5 py-0.5 text-[11px] font-semibold ${e.status === 'ok' ? 'bg-success/15 text-success' : 'bg-accent-wcm/15 text-accent-wcm'}`}
                >
                  {e.note}
                </span>
              ) : null}
            </Row>
          ))}
        </Block>
      ) : null}
      {sub === 'headings' ? <Headings h={onPage.headings} /> : null}
      {sub === 'links' ? <Links audit={audit} l={onPage.links} /> : null}
      {sub === 'images' ? <Images audit={audit} im={onPage.images} /> : null}
      {sub === 'speed' ? <Speed audit={audit} p={onPage.pagespeed} /> : null}
    </div>
  )
}
