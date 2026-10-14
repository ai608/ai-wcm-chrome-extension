import { Button } from '@/components/ui/button'
import type { FieldStatus as Status } from '@/stores/autosave-store'

interface FieldStatusProps {
  status: Status
  error?: string
  onRetry?: () => void
}

export function FieldStatus({ status, error, onRetry }: FieldStatusProps) {
  if (status === 'idle') return null
  if (status === 'pending') return <p className="text-[12px] text-muted-foreground">…</p>
  if (status === 'saving') return <p className="text-[12px] text-muted-foreground">Saving…</p>
  if (status === 'saved')
    return (
      <p className="text-[12px] text-muted-foreground" aria-live="polite">
        ✓ Saved
      </p>
    )
  return (
    <p className="flex items-center gap-1 text-[12px] text-destructive">
      <span>⚠ Not saved{error ? `: ${error}` : ''}</span>
      {onRetry ? (
        <Button variant="link" size="xs" className="h-auto p-0 text-[12px]" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </p>
  )
}
