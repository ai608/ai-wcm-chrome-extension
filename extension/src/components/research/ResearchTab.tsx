import { CompanyCard, GbpCard } from '@/components/research/BusinessTab'
import { startErrorMessage } from '@/components/research/ResearchMode'
import { CompetitorList, LocalCompetitorsForm } from '@/components/research/ResearchSubTabs'
import { Block, Chip, ExtLink, gradeClass, Row } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useContactResearch } from '@/hooks/research-queries'
import type { Audit } from '@/lib/api/research-types'
import { call } from '@/lib/messaging'
import { relativeTime } from '@/lib/time'

function Cards({ audit }: { audit: Audit }) {
  const { business, site, overview, research } = audit
  const services =
    site?.services.clusters.filter((c) => c.found > 0).map((c) => c.service.split(' (')[0]) ?? []
  const gbpWebsiteMatch = business?.gbp?.matched && business.gbp.websiteLinksToGbp
  return (
    <div className="flex flex-col gap-3">
      {business ? <GbpCard gbp={business.gbp} /> : <Skeleton className="h-24 w-full" />}
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
        {services.length ? (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {services.map((s) => (
              <Chip key={s}>{s}</Chip>
            ))}
          </div>
        ) : null}
        {site?.cities.cityPages.length ? (
          <div className="mt-2">
            <p className="text-[12px] text-muted-foreground">Areas served (website)</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {site.cities.cityPages.map((c) => (
                <Chip key={c}>{c}</Chip>
              ))}
            </div>
          </div>
        ) : null}
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
          <CompetitorList data={research.localCompetitors.data} />
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
      {overview?.score != null && overview.grade != null ? (
        <Block title="Website score">
          <div className="flex items-center gap-3">
            <div
              className={`flex size-12 shrink-0 items-center justify-center rounded-full text-2xl font-bold ${gradeClass(overview.grade)}`}
            >
              {overview.grade}
            </div>
            <p className="text-lg font-semibold">{overview.score} / 100</p>
          </div>
          <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-[13px]">
            {overview.topIssues.slice(0, 3).map((i) => (
              <li key={i.title}>{i.title}</li>
            ))}
          </ol>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => call('openReport', { auditId: audit.id })}
          >
            Open report
          </Button>
        </Block>
      ) : audit.status === 'queued' || audit.status === 'running' ? (
        <Block title="Website score">
          <p className="text-[13px] text-muted-foreground">
            Score appears when the audit finishes.
          </p>
        </Block>
      ) : null}
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
          Run research on this contact’s website and Google Business Profile.
        </p>
        <Button onClick={() => start.mutate(undefined)} disabled={start.isPending}>
          {start.isPending ? 'Starting…' : 'Run research'}
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
