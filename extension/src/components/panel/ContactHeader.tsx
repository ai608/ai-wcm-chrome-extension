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
    <div className="border-b border-border px-3 py-2">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            {contact.companyName || 'Unknown company'}
          </p>
          {sub ? <p className="truncate text-xs text-muted-foreground">{sub}</p> : null}
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
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          generated {relativeTime(script.generatedAt)}
        </p>
      ) : null}
    </div>
  )
}
