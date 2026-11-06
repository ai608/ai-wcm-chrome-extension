import { CameraIcon, WandSparklesIcon } from 'lucide-react'
import { CompanyCard, GbpCard } from '@/components/research/BusinessTab'
import { startErrorMessage } from '@/components/research/ResearchMode'
import { CompetitorList, LocalCompetitorsForm } from '@/components/research/ResearchSubTabs'
import { Block, Chip, ChipRow, ExtLink, Row } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useContactResearch } from '@/hooks/research-queries'
import { type Audit, auditBusy } from '@/lib/api/research-types'
import { relativeTime } from '@/lib/time'

// ponytail: UI only. No screenshot capture or concept generation exists yet; wire onClick when it does.
function ActionRows() {
  const label = 'text-[11px] font-semibold uppercase leading-tight text-muted-foreground'
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className={label}>Mobile experience</span>
        <Button variant="outline" size="xs" disabled title="Coming soon">
          <CameraIcon /> Capture screenshots
        </Button>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={label}>Redesign concept</span>
        <Button variant="outline" size="xs" disabled title="Coming soon">
          <WandSparklesIcon /> Build concept
        </Button>
      </div>
    </div>
  )
}

function Cards({ audit }: { audit: Audit }) {
  const { business, site, research } = audit
  const services =
    site?.services.clusters.filter((c) => c.found > 0).map((c) => c.service.split(' (')[0]) ?? []
  const description = audit.onPage?.essentials.find((e) => e.key === 'meta_description')?.value
  const gbpWebsiteMatch = business?.gbp?.matched && business.gbp.websiteLinksToGbp
  return (
    <div className="flex flex-col gap-3 [&>*+*]:border-t [&>*+*]:border-border [&>*+*]:pt-3">
      {business && (business.gbp || !auditBusy(audit)) ? (
        <GbpCard gbp={business.gbp} socials={business.socials} website={audit.url} bordered />
      ) : (
        <Skeleton className="h-24 w-full" />
      )}
      <Block title="Website">
        <Row label="URL">
          <ExtLink href={audit.url}>{audit.domain}</ExtLink>{' '}
          {gbpWebsiteMatch ? <Chip tone="good">VERIFIED</Chip> : null}
        </Row>
        {site ? (
          <Row label="Platform">
            {[site.platform.name, site.platform.detail].filter(Boolean).join(' · ')}
          </Row>
        ) : null}
        {audit.onPage ? (
          <Row label="Page title">
            {audit.onPage.essentials.find((e) => e.key === 'title')?.value ?? '-'}
          </Row>
        ) : null}
        {description ? <Row label="Description">{description}</Row> : null}
        {services.length ? <ChipRow label="Services" items={services} /> : null}
        {site?.cities.cityPages.length ? (
          <ChipRow label="Areas served (website)" items={site.cities.cityPages} />
        ) : null}
        <div className="mt-2">
          <ActionRows />
        </div>
      </Block>
      {business?.company ? (
        <CompanyCard company={business.company} />
      ) : (
        <Block title="Company">
          <p className="text-[13px] text-muted-foreground">
            Company data is not available for this audit.
          </p>
        </Block>
      )}
      <Block title="Local competitors">
        {research?.localCompetitors.state === 'ready' && research.localCompetitors.data ? (
          <CompetitorList data={research.localCompetitors.data} links />
        ) : research?.localCompetitors.state === 'running' ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <>
            {research?.localCompetitors.state === 'failed' ? (
              <Alert variant="destructive">
                <AlertDescription>
                  {research.localCompetitors.error ?? 'Couldn’t load competitors.'}
                </AlertDescription>
              </Alert>
            ) : null}
            <LocalCompetitorsForm audit={audit} compactForm />
          </>
        )}
      </Block>
    </div>
  )
}

export default function ResearchTab({ contactId }: { contactId: string }) {
  const { query, audit, start, timedOut } = useContactResearch(contactId)

  if (query.isPending) return <Skeleton className="h-32 w-full" />
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Couldn’t load research.</AlertDescription>
      </Alert>
    )
  }
  if (query.data?.reason === 'no_website') {
    return <p className="text-[14px] text-muted-foreground">This contact has no website in GHL.</p>
  }
  if (!audit) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-[14px] text-muted-foreground">
          Run an audit on this contact’s website and Google Business Profile.
        </p>
        <Button onClick={() => start.mutate(undefined)} disabled={start.isPending}>
          {start.isPending ? 'Starting…' : 'Run audit'}
        </Button>
        {start.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{startErrorMessage(start.error)}</AlertDescription>
          </Alert>
        ) : null}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <span className="flex-1">
          data as of {relativeTime(audit.finishedAt ?? audit.createdAt)}
        </span>
        <Button
          variant="outline"
          size="xs"
          onClick={() => start.mutate(true)}
          disabled={start.isPending}
        >
          Refresh research
        </Button>
      </div>
      {timedOut ? (
        <Alert>
          <AlertDescription>Still running… use Refresh research to retry.</AlertDescription>
        </Alert>
      ) : null}
      <Cards audit={audit} />
    </div>
  )
}
