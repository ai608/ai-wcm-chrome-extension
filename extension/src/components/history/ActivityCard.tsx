import { FileText, Mail, NotebookPen, Phone, StickyNote } from 'lucide-react'
import { useState } from 'react'
import { linkify } from '@/components/history/RichText'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import type { Activity } from '@/lib/api/types'
import { formatDateTime } from '@/lib/time'
import { cn } from '@/lib/utils'

const KIND_ICONS = {
  note: StickyNote,
  call: Phone,
  email: Mail,
  sms: NotebookPen,
  task: FileText,
} as const

export function ActivityCard({ activity }: { activity: Activity }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = KIND_ICONS[activity.kind]
  const long = activity.body.split('\n').length > 12 || activity.body.length > 800
  return (
    <Card className="px-3 py-2">
      <div className="flex items-center gap-1.5">
        <Icon className="size-3.5 text-muted-foreground" />
        <p className="flex-1 truncate text-xs font-semibold">{activity.source}</p>
        <p className="shrink-0 text-[11px] text-muted-foreground">
          {formatDateTime(activity.createdAt)}
        </p>
      </div>
      <div
        className={cn(
          'mt-1 text-xs leading-relaxed whitespace-pre-wrap',
          !expanded && 'line-clamp-12',
        )}
      >
        {linkify(activity.body)}
      </div>
      {long ? (
        <Button
          variant="link"
          size="xs"
          className="h-auto p-0 text-[11px]"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Show less' : 'Show more'}
        </Button>
      ) : null}
    </Card>
  )
}
