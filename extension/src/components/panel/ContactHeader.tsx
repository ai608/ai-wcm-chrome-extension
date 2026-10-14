import { RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Contact, PersonalizedScript } from '@/lib/api/types'
import { relativeTime } from '@/lib/time'

interface ContactHeaderProps {
  contact: Contact
  definitionVersion: number | undefined
  script: PersonalizedScript | undefined
  onRegenerate: () => void
}

export function ContactHeader({
  contact,
  definitionVersion,
  script,
  onRegenerate,
}: ContactHeaderProps) {
  const name = `${contact.firstName} ${contact.lastName}`.trim()
  const sub = [name || null, contact.phone || null, contact.city || null]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="border-b border-border px-4 py-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xl font-semibold leading-tight">
            {contact.companyName || 'Unknown company'}
          </p>
          {sub ? <p className="truncate text-[15px] text-muted-foreground">{sub}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {definitionVersion != null ? (
            <Badge variant="secondary">script v{definitionVersion}</Badge>
          ) : null}
          {script && script.scriptVersion !== definitionVersion ? (
            <Badge variant="outline">outdated</Badge>
          ) : null}
          <Button
            variant="ghost"
            size="icon-xs"
            title="Regenerate personalized lines"
            onClick={onRegenerate}
          >
            <RefreshCw />
          </Button>
        </div>
      </div>
      {script?.generatedAt ? (
        <p className="mt-1 text-[13px] text-muted-foreground">
          generated {relativeTime(script.generatedAt)}
        </p>
      ) : null}
    </div>
  )
}
