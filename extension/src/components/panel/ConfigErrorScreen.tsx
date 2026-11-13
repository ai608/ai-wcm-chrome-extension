import { PanelHeader } from '@/components/panel/PanelHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api/errors'
import { usePanelStore } from '@/stores/panel-store'

/** The call-mode settings (the CRM location and the booking link) could not be loaded. Without
 * them nothing in call mode can be checked, so say so and offer a retry, never a blank wait. */
export function ConfigErrorScreen({
  error,
  retrying,
  onRetry,
}: {
  error: unknown
  retrying: boolean
  onRetry: () => void
}) {
  const setView = usePanelStore((s) => s.setView)
  const detail = error instanceof ApiError ? error.message : null
  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader onSettings={() => setView('settings')} />
      <main className="flex flex-1 flex-col justify-center gap-3 p-4">
        <Alert variant="destructive">
          <AlertDescription>
            Could not load the assistant settings{detail ? `: ${detail}` : ''}. Check the connection
            and try again.
          </AlertDescription>
        </Alert>
        <Button onClick={onRetry} disabled={retrying} className="self-start">
          {retrying ? 'Trying…' : 'Try again'}
        </Button>
      </main>
    </div>
  )
}
