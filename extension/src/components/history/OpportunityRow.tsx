import { Badge } from '@/components/ui/badge'
import type { Opportunity } from '@/lib/api/types'
import { formatCurrency } from '@/lib/time'

const STATUS_VARIANTS = {
  open: 'default',
  won: 'success',
  lost: 'destructive',
  abandoned: 'secondary',
} as const

export function OpportunityRow({ opportunity }: { opportunity: Opportunity }) {
  const pipeline = [opportunity.pipelineName, opportunity.stageName].filter(Boolean).join(' · ')
  return (
    <div className="flex items-start justify-between gap-2 border-b border-border py-2 last:border-b-0">
      <div className="min-w-0">
        <p className="truncate text-xs font-semibold">{opportunity.name}</p>
        <Badge variant={STATUS_VARIANTS[opportunity.status]} className="mt-1">
          {opportunity.status}
        </Badge>
        {pipeline ? <p className="mt-0.5 text-[11px] text-muted-foreground">{pipeline}</p> : null}
      </div>
      <p className="shrink-0 text-xs font-medium">{formatCurrency(opportunity.monetaryValue)}</p>
    </div>
  )
}
