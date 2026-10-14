import { useState } from 'react'
import { queryClient } from '@/app/providers'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { logout, useAuth } from '@/hooks/use-auth'
import { getEnv } from '@/lib/env'
import { usePanelStore } from '@/stores/panel-store'

export function SettingsScreen() {
  const { user } = useAuth()
  const setView = usePanelStore((s) => s.setView)
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const env = getEnv()
  const version = browser.runtime.getManifest().version

  async function signOut() {
    setPending(true)
    try {
      await logout()
    } finally {
      queryClient.clear()
      setView('main')
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader />
      <main className="flex flex-1 flex-col gap-3 p-3">
        <Card>
          <CardContent className="flex flex-col gap-1 pt-4 text-[13px]">
            <p className="text-sm font-medium">{user?.fullName ?? 'Signed in'}</p>
            <p className="text-muted-foreground">{user?.email}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 pt-4 text-[13px] text-muted-foreground">
            <p>Version {version}</p>
            <p>API {env.apiBaseUrl}</p>
            <p>Mock {env.apiMock ? 'on' : 'off'}</p>
          </CardContent>
        </Card>
        {confirming ? (
          <div className="flex flex-col gap-2">
            <p className="text-[13px]">Sign out?</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={signOut} disabled={pending}>
                {pending ? 'Signing out…' : 'Sign out'}
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="outline" onClick={() => setConfirming(true)}>
            Sign out
          </Button>
        )}
        <Button variant="ghost" onClick={() => setView('main')}>
          Back
        </Button>
      </main>
    </div>
  )
}
