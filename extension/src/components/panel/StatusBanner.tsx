import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api/errors'

export function bannerMessage(err: ApiError): string {
  if (err.code === 'network_error') return "You're offline"
  if (err.code === 'invalid_response') return 'Unexpected response from server'
  if (err.code === 'upstream_error') return 'GHL/O4 temporarily unavailable'
  return err.message
}

export function StatusBanner({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!(error instanceof ApiError)) return null
  if (
    error.code !== 'network_error' &&
    error.code !== 'invalid_response' &&
    error.code !== 'upstream_error'
  ) {
    return null
  }
  return (
    <Alert variant="destructive" className="rounded-none border-x-0 border-t-0">
      <AlertDescription className="flex items-center gap-2">
        <span className="flex-1">{bannerMessage(error)}</span>
        {onRetry ? (
          <Button variant="outline" size="xs" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}
