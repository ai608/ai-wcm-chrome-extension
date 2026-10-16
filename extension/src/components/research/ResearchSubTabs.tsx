import { useState } from 'react'
import { Block, Chip, StatBox, SubTabs } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useRunOnDemand } from '@/hooks/research-queries'
import type { Audit, OnDemand } from '@/lib/api/research-types'
import { usePanelStore } from '@/stores/panel-store'

type Sub = 'domain' | 'local' | 'ai'
const SUBS: { value: Sub; label: string }[] = [
  { value: 'domain', label: 'Domain Overview' },
  { value: 'local', label: 'Local Competitors' },
  { value: 'ai', label: 'AI Visibility' },
]

const compact = new Intl.NumberFormat('en-US', { notation: 'compact' })
const n = (v: number | null) => (v == null ? '-' : compact.format(v))

function State<T>({
  od,
  onRetry,
  children,
}: {
  od: OnDemand<T>
  onRetry: () => void
  children: (data: T) => React.ReactElement
}) {
  if (od.state === 'running') {
    return (
      <div className="flex flex-col gap-2" role="status">
        <Skeleton className="h-16 w-full" />
        <p className="text-[13px] text-muted-foreground">Running…</p>
      </div>
    )
  }
  if (od.state === 'failed') {
    return (
      <Alert variant="destructive">
        <AlertDescription className="flex items-center gap-2">
          <span className="flex-1">{od.error ?? 'The check failed.'}</span>
          <Button size="xs" variant="outline" onClick={onRetry}>
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  return od.data ? children(od.data) : null
}

export function defaultService(audit: Audit): string {
  const top = audit.site?.services.clusters.find((c) => c.found > 0)?.service
  return top ? (top.split(' (')[0] ?? top).toLowerCase() : 'med spa'
}

export function defaultLocation(audit: Audit): string {
  const m = /,\s*([^,]+),\s*([A-Z]{2})\b/.exec(audit.business?.gbp?.address ?? '')
  return m ? `${m[1]}, ${m[2]}` : ''
}

export function LocalCompetitorsForm({
  audit,
  compactForm,
}: {
  audit: Audit
  compactForm?: boolean
}) {
  const run = useRunOnDemand(audit.id, audit.domain)
  const [query, setQuery] = useState(defaultService(audit))
  const [location, setLocation] = useState(defaultLocation(audit))
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        run.mutate({ kind: 'local', query, location })
      }}
    >
      {compactForm ? null : (
        <p className="text-[13px] text-muted-foreground">
          Top Google Maps results for this search; flags where this clinic ranks.
        </p>
      )}
      <Label htmlFor="lc-q">Search</Label>
      <Input id="lc-q" value={query} onChange={(e) => setQuery(e.target.value)} />
      <Label htmlFor="lc-l">Location</Label>
      <Input id="lc-l" value={location} onChange={(e) => setLocation(e.target.value)} />
      <Button type="submit" disabled={run.isPending}>
        Find competitors
      </Button>
    </form>
  )
}

export function CompetitorList({
  data,
}: {
  data: import('@/lib/api/research-types').LocalCompetitors
}) {
  const me = data.items.find((i) => i.isThisBusiness)
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] text-muted-foreground">
        “{data.query}” in {data.location}
      </p>
      <ol className="flex flex-col gap-1 text-[13px]">
        {data.items.map((i) => (
          <li
            key={i.rank}
            className={`rounded-md border px-2 py-1.5 ${i.isThisBusiness ? 'border-primary bg-primary/5' : 'border-border'}`}
          >
            {i.rank}. <span className="font-medium">{i.name}</span>
            {i.rating != null ? ` · ★ ${i.rating} (${i.reviewCount ?? 0})` : ''}
            {i.isThisBusiness ? <span className="ml-2 font-semibold">This clinic</span> : null}
          </li>
        ))}
      </ol>
      {me ? null : (
        <p className="text-[13px] text-destructive">Not in the top {data.items.length}.</p>
      )}
    </div>
  )
}

export function ResearchSubTabs({ audit }: { audit: Audit }) {
  const sub = (usePanelStore((s) => s.researchSubTab.research) as Sub | undefined) ?? 'domain'
  const setSub = usePanelStore((s) => s.setResearchSubTab)
  const run = useRunOnDemand(audit.id, audit.domain)
  const r = audit.research
  const [prompts, setPrompts] = useState(() => {
    const svc = defaultService(audit)
    const city = defaultLocation(audit).split(',')[0] || 'your city'
    return [
      `best ${svc} in ${city}`,
      `who should I see for ${svc} near ${city}`,
      `top rated ${svc} in ${city}`,
    ]
  })
  if (!r) return null
  return (
    <div className="flex flex-col gap-3">
      <SubTabs value={sub} onChange={(v) => setSub('research', v)} items={SUBS} />
      {sub === 'domain' ? (
        r.domainOverview.state === 'not_run' ? (
          <Block title="Domain Overview">
            <p className="mb-2 text-[13px] text-muted-foreground">
              Ahrefs domain rating, organic traffic, keywords and backlinks. Uses Ahrefs API units.
            </p>
            <Button onClick={() => run.mutate({ kind: 'domain' })} disabled={run.isPending}>
              Pull domain overview
            </Button>
          </Block>
        ) : (
          <State od={r.domainOverview} onRetry={() => run.mutate({ kind: 'domain' })}>
            {(d) => (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-2">
                  <StatBox label="DR" value={d.domainRating ?? '-'} />
                  <StatBox label="Traffic" value={n(d.organicTraffic)} />
                  <StatBox label="Keywords" value={n(d.organicKeywords)} />
                  <StatBox label="Ref. domains" value={n(d.referringDomains)} />
                  <StatBox label="Backlinks" value={n(d.backlinks)} />
                </div>
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="font-medium">Keyword</th>
                      <th className="font-medium">Pos.</th>
                      <th className="font-medium">Vol.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.topKeywords.slice(0, 20).map((k) => (
                      <tr key={k.keyword} className="border-t border-border">
                        <td className="py-1">{k.keyword}</td>
                        <td>{k.position}</td>
                        <td>{n(k.volume)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </State>
        )
      ) : null}
      {sub === 'local' ? (
        <Block title="Local Competitors">
          {r.localCompetitors.state === 'not_run' ? (
            <LocalCompetitorsForm audit={audit} />
          ) : (
            <State od={r.localCompetitors} onRetry={() => run.mutate({ kind: 'local' })}>
              {(d) => <CompetitorList data={d} />}
            </State>
          )}
        </Block>
      ) : null}
      {sub === 'ai' ? (
        <Block title="AI Visibility">
          {r.aiVisibility.state === 'not_run' ? (
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                run.mutate({ kind: 'ai', prompts: prompts.filter((p) => p.trim()).slice(0, 3) })
              }}
            >
              <p className="text-[13px] text-muted-foreground">
                Asks ChatGPT, Gemini, Perplexity and Claude (via web search) and shows whether this
                clinic is mentioned. ~20–40 s.
              </p>
              {prompts.map((p, i) => (
                <Input
                  // biome-ignore lint/suspicious/noArrayIndexKey: fixed three slots
                  key={i}
                  aria-label={`Prompt ${i + 1}`}
                  value={p}
                  onChange={(e) =>
                    setPrompts(prompts.map((x, j) => (j === i ? e.target.value : x)))
                  }
                />
              ))}
              <Button type="submit" disabled={run.isPending}>
                Check AI visibility
              </Button>
            </form>
          ) : (
            <State od={r.aiVisibility} onRetry={() => run.mutate({ kind: 'ai', prompts })}>
              {(d) => (
                <ul className="flex flex-col gap-2 text-[13px]">
                  {d.engines.map((e) => (
                    <li key={e.engine} className="rounded-md border border-border p-2">
                      <div className="flex items-center gap-2">
                        <span className="flex-1 font-medium">{e.engine}</span>
                        <Chip tone={e.cited ? 'good' : 'bad'}>
                          {e.cited ? '✓ Cited' : '✗ Not cited'}
                        </Chip>
                      </div>
                      {e.citedBusinesses.length ? (
                        <p className="mt-1 text-muted-foreground">
                          Mentioned instead: {e.citedBusinesses.join(', ')}
                        </p>
                      ) : null}
                      <details className="mt-1">
                        <summary className="cursor-pointer text-[12px]">Answer excerpt</summary>
                        <p className="mt-1 text-[12px] text-muted-foreground">{e.answerExcerpt}</p>
                      </details>
                    </li>
                  ))}
                </ul>
              )}
            </State>
          )}
        </Block>
      ) : null}
    </div>
  )
}
