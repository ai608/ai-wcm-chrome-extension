import { BusinessTab } from '@/components/research/BusinessTab'
import { startErrorMessage } from '@/components/research/ResearchMode'
import { CompetitorList, LocalCompetitorsForm } from '@/components/research/ResearchSubTabs'
import { Block } from '@/components/research/shared'
import { WebsiteSummary } from '@/components/research/WebsiteSummary'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useContactResearch } from '@/hooks/research-queries'
import { type Audit, auditBusy } from '@/lib/api/research-types'
import { relativeTime } from '@/lib/time'

function LocalCompetitors({ audit }: { audit: Audit }) {
  const research = audit.research
  return (
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
  )
}

function Cards({ audit }: { audit: Audit }) {
  const { business } = audit
  const competitors = <LocalCompetitors audit={audit} />

  // No business section yet — still share WebsiteSummary + competitors layout.
  if (!business) {
    return (
      <div className="flex flex-col gap-3 [&>*+*]:border-t [&>*+*]:border-border [&>*+*]:pt-3">
        <Skeleton className="h-24 w-full" />
        <WebsiteSummary audit={audit} showActions />
        <Block title="Company">
          <p className="text-[14px] text-foreground/80">
            Company data is not available for this audit.
          </p>
        </Block>
        {competitors}
      </div>
    )
  }

  return (
    <BusinessTab
      business={business}
      audit={audit}
      website={audit.url}
      bordered
      showWebsiteActions
      gbpPending={auditBusy(audit) && !business.gbp}
      extra={competitors}
    />
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
          <AlertDescription>
            This is taking longer than usual. It updates here by itself and stops on its own after a
            few minutes at most.
          </AlertDescription>
        </Alert>
      ) : null}
      <Cards audit={audit} />
    </div>
  )
}
