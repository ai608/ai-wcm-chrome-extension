import { useState } from 'react'
import { Block, ExtLink, FilterChips, Row, StatBox, SubTabs } from '@/components/research/shared'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toast'
import type { Audit, OnPageSection } from '@/lib/api/research-types'
import { downloadCsv, toCsv } from '@/lib/csv'
import { usePanelStore } from '@/stores/panel-store'

type Sub = 'essentials' | 'headings' | 'links' | 'images' | 'speed'
const SUBS: { value: Sub; label: string }[] = [
  { value: 'essentials', label: 'Essentials' },
  { value: 'headings', label: 'Headings' },
  { value: 'links', label: 'Links' },
  { value: 'images', label: 'Images' },
  { value: 'speed', label: 'Speed' },
]

function Headings({ h }: { h: OnPageSection['headings'] }) {
  const h1 =
    h.h1Count === 1 ? 'Exactly one H1 ✓' : h.h1Count === 0 ? 'Missing H1' : `${h.h1Count} H1s`
  const text = h.outline.map((o) => `${'  '.repeat(o.level - 1)}H${o.level} ${o.text}`).join('\n')
  return (
    <div className="flex flex-col gap-2">
      <Row label="H1 check" status={h.h1Count === 1 ? 'ok' : 'fail'}>
        {h1}
      </Row>
      <ul className="flex flex-col gap-1 text-[13px]">
        {h.outline.map((o, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static outline, order is identity
          <li key={i} style={{ paddingLeft: (o.level - 1) * 14 }} className="flex gap-2">
            <span className="rounded bg-muted px-1 text-[11px] font-semibold">H{o.level}</span>
            <span>{o.text}</span>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          navigator.clipboard
            .writeText(text)
            .then(() => toast('Copied'))
            .catch(() => toast('Couldn’t copy'))
        }
      >
        Copy outline
      </Button>
    </div>
  )
}

function Links({ audit, l }: { audit: Audit; l: OnPageSection['links'] }) {
  const [f, setF] = useState<'all' | 'internal' | 'external' | 'nofollow'>('all')
  const items = l.items.filter((i) =>
    f === 'all' ? true : f === 'nofollow' ? i.nofollow : i.kind === f,
  )
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <StatBox label="Internal" value={l.internal} />
        <StatBox label="External" value={l.external} />
        <StatBox label="Nofollow" value={l.nofollow} />
      </div>
      <FilterChips
        value={f}
        onChange={setF}
        items={[
          { value: 'all', label: 'All' },
          { value: 'internal', label: 'Internal' },
          { value: 'external', label: 'External' },
          { value: 'nofollow', label: 'Nofollow' },
        ]}
      />
      <ul className="flex flex-col gap-1.5 text-[13px]">
        {items.map((i) => (
          <li key={`${i.href}-${i.text}`} className="rounded-md border border-border px-2 py-1.5">
            <span className="mr-2 rounded bg-muted px-1 text-[11px] uppercase">{i.kind}</span>
            {i.text || <span className="text-muted-foreground">(no anchor text)</span>}
            <p className="break-all text-[12px] text-muted-foreground">{i.href}</p>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          downloadCsv(
            audit.domain,
            'links',
            toCsv(
              items.map((i) => ({
                href: i.href,
                text: i.text,
                kind: i.kind,
                nofollow: i.nofollow,
              })),
            ),
          )
        }
      >
        Export {items.length} links to CSV
      </Button>
    </div>
  )
}

function Images({ audit, im }: { audit: Audit; im: OnPageSection['images'] }) {
  const [f, setF] = useState<'all' | 'missing'>('all')
  const items = im.items.filter((i) => (f === 'missing' ? !i.alt : true))
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <StatBox label="Images" value={im.total} />
        <StatBox label="Missing alt" value={im.missingAlt} tone={im.missingAlt ? 'bad' : 'good'} />
        <StatBox label="Lazy loaded" value={im.lazy} />
      </div>
      <FilterChips
        value={f}
        onChange={setF}
        items={[
          { value: 'all', label: 'All' },
          { value: 'missing', label: 'Missing alt' },
        ]}
      />
      <ul className="flex flex-col gap-1.5 text-[13px]">
        {items.map((i) => (
          <li key={i.src} className="rounded-md border border-border px-2 py-1.5">
            {i.alt ? i.alt : <span className="font-semibold text-destructive">MISSING ALT</span>}
            <p className="break-all text-[12px] text-muted-foreground">
              {i.src.split('/').pop()}
              {i.width && i.height ? ` · ${i.width}×${i.height}` : ''}
            </p>
          </li>
        ))}
      </ul>
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          downloadCsv(
            audit.domain,
            'images',
            toCsv(items.map((i) => ({ src: i.src, alt: i.alt, width: i.width, height: i.height }))),
          )
        }
      >
        Export {items.length} images to CSV
      </Button>
    </div>
  )
}

function Speed({ audit, p }: { audit: Audit; p: OnPageSection['pagespeed'] }) {
  if (!p)
    return <p className="text-[13px] text-muted-foreground">PageSpeed data isn’t available.</p>
  const bars: [string, number | null][] = [
    ['Performance', p.mobilePerformance],
    ['SEO', p.seo],
    ['Accessibility', p.accessibility],
    ['Best practices', p.bestPractices],
  ]
  return (
    <div className="flex flex-col gap-2">
      {bars.map(([label, v]) => (
        <div key={label}>
          <div className="flex justify-between text-[13px]">
            <span>{label} (mobile)</span>
            <span className="font-medium">{v ?? '-'}</span>
          </div>
          <Progress
            value={v ?? 0}
            indicatorClassName={
              (v ?? 0) >= 90 ? 'bg-success' : (v ?? 0) >= 50 ? 'bg-accent-wcm' : 'bg-destructive'
            }
          />
        </div>
      ))}
      <Row label="LCP">{p.lcpMs != null ? `${(p.lcpMs / 1000).toFixed(1)} s` : '-'}</Row>
      <Row label="CLS">{p.cls ?? '-'}</Row>
      <ExtLink href={`https://pagespeed.web.dev/analysis?url=${encodeURIComponent(audit.url)}`}>
        Open in PageSpeed
      </ExtLink>
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
