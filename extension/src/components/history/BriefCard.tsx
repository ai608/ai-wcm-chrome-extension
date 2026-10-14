import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { relativeTime } from '@/lib/time'

const NINETY_DAYS_MS = 90 * 86_400_000

export function BriefCard({
  brief,
  lastContactedAt,
}: {
  brief: { text: string; generatedAt: string }
  lastContactedAt: string | null
}) {
  const stale =
    lastContactedAt == null || Date.now() - new Date(lastContactedAt).getTime() > NINETY_DAYS_MS
  return (
    <Card className="border-primary/30 bg-primary/5 px-3 py-2">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-xs font-semibold">Brief</p>
        {stale ? (
          <Badge variant="warning">
            {lastContactedAt == null
              ? 'Never contacted'
              : `Not contacted in ${relativeTime(lastContactedAt)}`}
          </Badge>
        ) : null}
      </div>
      <p className="mt-1 text-xs leading-relaxed">{brief.text}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        generated {relativeTime(brief.generatedAt)}
      </p>
    </Card>
  )
}
