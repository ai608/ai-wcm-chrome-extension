import { Globe, Star } from 'lucide-react'
import { useState } from 'react'
import { AiReportPanel } from '@/components/research/AiReportPanel'
import { Block, StatBox, SubTabs } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useRunOnDemand } from '@/hooks/research-queries'
import type { Audit, OnDemand } from '@/lib/api/research-types'
import { getEnv } from '@/lib/env'
import { cn } from '@/lib/utils'
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
  // With the clinic's coordinates, the clinic address (shown prefilled) searches around the clinic,
  // what a nearby patient sees. Any other typed place wins.
  const near = audit.business?.gbp?.lat != null && audit.business?.gbp?.lng != null
  const clinicAddress = audit.business?.gbp?.address ?? ''
  const [location, setLocation] = useState(near ? clinicAddress : defaultLocation(audit))
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        run.mutate({
          kind: 'local',
          query,
          location: near && location === clinicAddress ? '' : location,
        })
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
      <Input
        id="lc-l"
        value={location}
        placeholder={near ? 'Around the clinic' : 'City, State'}
        onChange={(e) => setLocation(e.target.value)}
      />
      {near ? (
        <p className="text-[12px] text-muted-foreground">
          Searches within 8 km of the clinic. Type a city to search somewhere else.
        </p>
      ) : null}
      <Button type="submit" disabled={run.isPending}>
        Find competitors
      </Button>
      {run.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {run.error instanceof Error ? run.error.message : 'Couldn’t find competitors.'}
          </AlertDescription>
        </Alert>
      ) : null}
    </form>
  )
}

function siteHref(website: string | null): string | null {
  if (!website) return null
  try {
    const url = new URL(website)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : null
  } catch {
    return null
  }
}

export function CompetitorList({
  data,
  links = false,
}: {
  data: import('@/lib/api/research-types').LocalCompetitors
  /** Panel lists can open the listing's site. The printed report leaves this off. */
  links?: boolean
}) {
  const me = data.items.find((i) => i.isThisBusiness)
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] text-muted-foreground">
        “{data.query}” {data.location.startsWith('within') ? data.location : `in ${data.location}`}
      </p>
      <ol className="overflow-hidden rounded-lg border border-border">
        {data.items.map((item) => {
          const href = links ? siteHref(item.website) : null
          return (
            <li
              key={item.rank}
              className={cn(
                'grid items-center gap-x-2 border-b border-border px-2.5 py-1.5 last:border-b-0',
                links
                  ? 'grid-cols-[1.25rem_minmax(0,1fr)_4.75rem_1.5rem]'
                  : 'grid-cols-[1.25rem_minmax(0,1fr)_4.75rem]',
                item.isThisBusiness && 'bg-primary/5 shadow-[inset_2px_0_0_0_var(--primary)]',
              )}
            >
              <span
                className={cn(
                  'text-right text-[12px] font-medium tabular-nums',
                  item.isThisBusiness ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {item.rank}
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium leading-snug">{item.name}</p>
                {item.isThisBusiness ? (
                  <p className="text-[11px] font-medium leading-4 text-primary">This clinic</p>
                ) : null}
              </div>
              <div className="flex flex-col items-end leading-4">
                {item.rating != null ? (
                  <>
                    <p className="flex items-center gap-0.5 text-[12px] font-medium tabular-nums">
                      <Star
                        className="size-3 shrink-0 fill-accent-wcm text-accent-wcm"
                        aria-hidden="true"
                      />
                      {item.rating}
                    </p>
                    <p className="whitespace-nowrap text-[11px] text-muted-foreground tabular-nums">
                      {(item.reviewCount ?? 0).toLocaleString('en-US')} reviews
                    </p>
                  </>
                ) : null}
              </div>
              {links ? (
                href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label="Visit site"
                    className="inline-flex size-6 items-center justify-center justify-self-end rounded-md text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Globe className="size-3.5" aria-hidden="true" />
                  </a>
                ) : (
                  <span className="size-6 justify-self-end" aria-hidden="true" />
                )
              ) : null}
            </li>
          )
        })}
      </ol>
      {me ? null : (
        <p className="text-[13px] text-destructive">
          Not found in the top {data.items.length}. The listing may use a different name or website.
        </p>
      )}
      <p className="text-[12px] text-muted-foreground">
        Order of one Google Maps search, so the rank is approximate.
      </p>
    </div>
  )
}

export function ResearchSubTabs({ audit }: { audit: Audit }) {
  const selected = usePanelStore((s) => s.researchSubTab.research) as Sub | undefined
  const subs = getEnv().apiMock ? SUBS : SUBS.filter((item) => item.value !== 'domain')
  const sub = subs.some((item) => item.value === selected) ? selected : subs[0]?.value
  const setSub = usePanelStore((s) => s.setResearchSubTab)
  const run = useRunOnDemand(audit.id, audit.domain)
  const r = audit.research
  if (!r) return null
  return (
    <div className="flex flex-col gap-3">
      <SubTabs value={sub ?? 'local'} onChange={(v) => setSub('research', v)} items={subs} />
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
              {(d) => <CompetitorList data={d} links />}
            </State>
          )}
        </Block>
      ) : null}
      {sub === 'ai' ? (
        <Block title="AI Visibility">
          <AiReportPanel audit={audit} />
        </Block>
      ) : null}
    </div>
  )
}
