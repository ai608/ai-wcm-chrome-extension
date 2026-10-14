import { Button } from '@/components/ui/button'
import type { FieldStatus } from '@/stores/autosave-store'

interface FieldStatusProps {
  status: FieldStatus
  error?: string
  onRetry?: () => void
}

export function FieldStatus({ status, error, onRetry }: FieldStatusProps) {
  if (status === 'idle') return null
  if (status === 'pending') return <p className="text-[11px] text-muted-foreground">…</p>
  if (status === 'saving') return <p className="text-[11px] text-muted-foreground">Saving…</p>
  if (status === 'saved')
    return (
      <p className="text-[11px] text-muted-foreground" aria-live="polite">
        ✓ Saved
      </p>
    )
  return (
    <p className="flex items-center gap-1 text-[11px] text-destructive">
      <span>⚠ Not saved{error ? `: ${error}` : ''}</span>
      {onRetry ? (
        <Button variant="link" size="xs" className="h-auto p-0 text-[11px]" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </p>
  )
}
