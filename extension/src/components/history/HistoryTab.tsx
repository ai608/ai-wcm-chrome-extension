import { ActivityCard } from '@/components/history/ActivityCard'
import { BriefCard } from '@/components/history/BriefCard'
import { OpportunityRow } from '@/components/history/OpportunityRow'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useHistoryQuery } from '@/hooks/queries'

export function HistoryTab({ contactId }: { contactId: string }) {
  const historyQuery = useHistoryQuery(contactId)

  if (historyQuery.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-label="Loading history">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (historyQuery.isError || !historyQuery.data) {
    return (
      <Alert variant="destructive">
        <AlertDescription className="flex items-center gap-2">
          <span className="flex-1">Couldn&apos;t load history.</span>
          <Button variant="outline" size="xs" onClick={() => historyQuery.refetch()}>
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }

  const { brief, activities, opportunities, lastContactedAt } = historyQuery.data
  const sorted = [...activities].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )

  return (
    <div className="flex flex-col gap-3">
      {brief ? <BriefCard brief={brief} lastContactedAt={lastContactedAt} /> : null}
      {sorted.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No activity yet</p>
      ) : (
        sorted.map((a) => <ActivityCard key={a.id} activity={a} />)
      )}
      <p className="text-[14px] font-semibold text-foreground">Opportunities</p>
      {opportunities.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No opportunities</p>
      ) : (
        <div>
          {opportunities.map((o) => (
            <OpportunityRow key={o.id} opportunity={o} />
          ))}
        </div>
      )}
    </div>
  )
}
