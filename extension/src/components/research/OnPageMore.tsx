import type { ReactNode } from 'react'
import { Chip, SectionTitle } from '@/components/research/shared'
import type { LinkRow, OnPageSection, PageField } from '@/lib/api/research-types'

function pathOf(url: string): string {
  try {
    const u = new URL(url)
    return `${u.pathname}${u.search}` || '/'
  } catch {
    return url
  }
}

const kb = (bytes: number) => `${Math.round(bytes / 1000).toLocaleString('en-US')} KB`
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

function List({ title, items }: Readonly<{ title: string; items: ReactNode[] }>) {
  if (items.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-[13px] font-semibold text-foreground">{title}</p>
      <ul className="mt-1 flex flex-col gap-1 text-[12px] text-muted-foreground">
        {items.map((item, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: a short read-only list
          <li key={i} className="break-all">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function linkLine(r: LinkRow): ReactNode {
  return (
    <>
      <span className="text-foreground">{pathOf(r.url)}</span>
      {r.status ? ` · ${r.status}` : ''}
      {r.hops > 0 ? ` · ${plural(r.hops, 'redirect', 'redirects')} to ${pathOf(r.final)}` : ''}
      {r.foundOn ? ` · on ${pathOf(r.foundOn)}` : ''}
    </>
  )
}

/** Broken links, redirects, the one-address check and page structure. Rendered under Links. */
export function LinkCheck({ onPage }: Readonly<{ onPage: OnPageSection }>) {
  const { linkCheck: lc, probes, structure } = onPage
  if (!lc && !probes && !structure) return null // an audit saved before these checks
  const hosts = probes?.ran ? probes.hosts.filter((h) => h.status != null) : []
  return (
    <section className="mt-4 flex flex-col" aria-label="Link and redirect check">
      <SectionTitle>Link and redirect check</SectionTitle>
      {probes && !probes.ran ? (
        <p className="text-[13px] text-muted-foreground">
          Skipped for the links we did not read: this site blocks direct requests, so a result could
          be wrong. The pages we did read were still checked.
        </p>
      ) : null}
      {lc ? (
        <p className="text-[13px] text-muted-foreground tabular-nums">
          {plural(lc.checked, 'link', 'links')} checked · {lc.broken.length} broken ·{' '}
          {plural(lc.chains.length, 'redirect chain', 'redirect chains')} ·{' '}
          {plural(lc.redirects.length, 'redirect', 'redirects')}
          {probes && probes.timedOut > 0 ? ` · ${probes.timedOut} not finished in time` : ''}
        </p>
      ) : null}
      <List title="Broken links" items={(lc?.broken ?? []).map(linkLine)} />
      <List title="Redirect chains" items={(lc?.chains ?? []).map(linkLine)} />
      <List
        title="One address for the site"
        items={hosts.map((h) => (
          <>
            <span className="text-foreground">{h.url}</span> ends at{' '}
            <span className="text-foreground">{h.final}</span>
          </>
        ))}
      />
      {structure ? (
        <>
          <p className="mt-3 text-[13px] text-muted-foreground tabular-nums">
            Deepest page: {plural(structure.maxDepth, 'click', 'clicks')} from the home page.
          </p>
          <List title="3 or more clicks from home" items={structure.deep.map(pathOf)} />
          <List
            title="No booking or contact link in the text"
            items={structure.noBookingLink.map(pathOf)}
          />
          <List title="Link to no other service" items={structure.noRelatedLinks.map(pathOf)} />
        </>
      ) : null}
    </section>
  )
}

const TONE: Record<string, 'good' | 'warn' | 'bad'> = { FAST: 'good', AVERAGE: 'warn', SLOW: 'bad' }
const WORD: Record<string, string> = { FAST: 'Good', AVERAGE: 'Needs work', SLOW: 'Poor' }

function Metric({
  name,
  value,
  verdict,
}: Readonly<{ name: string; value: string | null; verdict: string | null }>) {
  if (value == null) return null
  return (
    <li className="flex items-center gap-2 py-2">
      <span className="flex-1 text-[13px] font-semibold text-foreground">{name}</span>
      <span className="text-[13px] font-semibold tabular-nums">{value}</span>
      {verdict ? <Chip tone={TONE[verdict] ?? 'default'}>{WORD[verdict] ?? verdict}</Chip> : null}
    </li>
  )
}

function RealVisitors({ field }: Readonly<{ field: PageField | null }>) {
  if (!field) {
    return (
      <p className="text-[13px] text-muted-foreground">
        No real-visitor data. Google needs more Chrome visits to this site before it publishes
        numbers, which is common for a small site.
      </p>
    )
  }
  return (
    <>
      <p className="text-[12px] text-muted-foreground">
        Measured on real phones, {field.source === 'url' ? 'for this page' : 'for the whole site'}.
      </p>
      <ul className="divide-y divide-border">
        <Metric
          name="Main content shows"
          value={field.lcpMs == null ? null : `${(field.lcpMs / 1000).toFixed(1)} s`}
          verdict={field.lcp}
        />
        <Metric
          name="Reacts to a tap"
          value={field.inpMs == null ? null : `${Math.round(field.inpMs)} ms`}
          verdict={field.inp}
        />
        <Metric
          name="Page stays still"
          value={field.cls == null ? null : field.cls.toFixed(2)}
          verdict={field.clsCategory}
        />
      </ul>
    </>
  )
}

function Phone({
  label,
  ok,
  bad,
}: Readonly<{ label: string; ok: boolean | null | undefined; bad: string }>) {
  if (ok == null) return null
  return (
    <li className="flex items-center gap-2 py-2">
      <span className="flex-1 text-[13px] font-semibold text-foreground">{label}</span>
      <Chip tone={ok ? 'good' : 'bad'}>{ok ? 'Fine' : bad}</Chip>
    </li>
  )
}

/** Real visitors and phones, under the Lighthouse scores. */
export function SpeedExtras({ p }: Readonly<{ p: OnPageSection['pagespeed'] }>) {
  if (!p) return null
  const phones = p.tapTargetsOk != null || p.zoomOk != null
  if (p.field === undefined && !phones) return null // saved before these were measured
  return (
    <div className="mt-4 flex flex-col gap-4">
      {p.field !== undefined ? (
        <section className="flex flex-col" aria-label="Real visitors">
          <SectionTitle>Real visitors</SectionTitle>
          <RealVisitors field={p.field} />
        </section>
      ) : null}
      {phones ? (
        <section className="flex flex-col" aria-label="On phones">
          <SectionTitle>On phones</SectionTitle>
          <ul className="divide-y divide-border">
            <Phone
              label="Buttons and links are easy to tap"
              ok={p.tapTargetsOk}
              bad="Too small or close"
            />
            <Phone label="Visitors can zoom in" ok={p.zoomOk} bad="Zoom is blocked" />
          </ul>
        </section>
      ) : null}
    </div>
  )
}

/** Picture size and background findings, under the image list. */
export function ImageExtras({ im }: Readonly<{ im: OnPageSection['images'] }>) {
  const large = im.large ?? []
  if (im.noDimensions == null && im.cssBackgrounds == null && large.length === 0) return null
  return (
    <section className="mt-4 flex flex-col" aria-label="Picture size and placement">
      <SectionTitle>Picture size and placement</SectionTitle>
      <ul className="flex flex-col gap-1 text-[13px] text-muted-foreground tabular-nums">
        {im.noDimensions != null ? (
          <li>{plural(im.noDimensions, 'image has', 'images have')} no width and height.</li>
        ) : null}
        {im.cssBackgrounds != null ? (
          <li>{plural(im.cssBackgrounds, 'picture is', 'pictures are')} set as CSS backgrounds.</li>
        ) : null}
        {im.sizesChecked != null && im.sizesChecked > 0 ? (
          <li>
            {plural(im.sizesChecked, 'home page image', 'home page images')} measured;{' '}
            {large.length} over 400 KB.
          </li>
        ) : null}
      </ul>
      <List title="Large images" items={large.map((i) => `${pathOf(i.url)} · ${kb(i.bytes)}`)} />
    </section>
  )
}
