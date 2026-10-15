import { ArrowLeft, LogOut } from 'lucide-react'
import { useState } from 'react'
import { queryClient } from '@/app/providers'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { logout } from '@/hooks/use-auth'
import type { User } from '@/lib/api/types'
import { getEnv } from '@/lib/env'
import { usePanelStore } from '@/stores/panel-store'

export function SettingsScreen({ user }: { user: User }) {
  const setView = usePanelStore((s) => s.setView)
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const env = getEnv()
  const version = browser.runtime.getManifest().version
  const name = user.fullName.trim() || 'Signed in'
  const initial = (user.fullName.trim() || user.email).charAt(0).toUpperCase()

  async function signOut() {
    setPending(true)
    setSignOutError(null)
    try {
      await logout()
      queryClient.clear()
      setView('main')
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : 'Could not sign out. Try again.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PanelHeader mode="Settings" />
      <main className="min-h-0 flex-1 overflow-y-auto bg-muted/30 px-4 py-4">
        <div className="mx-auto flex w-full max-w-lg flex-col gap-6">
          <Button
            variant="ghost"
            className="-ml-2 h-9 self-start px-2 text-muted-foreground hover:text-foreground"
            onClick={() => setView('main')}
          >
            <ArrowLeft aria-hidden="true" />
            Back to assistant
          </Button>

          <section aria-labelledby="settings-account">
            <h1 id="settings-account" className="mb-3 text-sm font-semibold">
              Account
            </h1>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-4">
              <div
                aria-hidden="true"
                className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-base font-semibold text-primary"
              >
                {initial}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{name}</p>
                <p className="break-all text-[12px] leading-5 text-muted-foreground">
                  {user.email}
                </p>
              </div>
            </div>
          </section>

          <section aria-labelledby="settings-connection">
            <h2 id="settings-connection" className="mb-3 text-sm font-semibold">
              Connection
            </h2>
            <dl className="divide-y divide-border rounded-xl border border-border bg-card px-4">
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-[12px] text-muted-foreground">Data source</dt>
                <dd className="text-[12px] font-medium">
                  {env.apiMock ? 'Mock data' : 'Live API'}
                </dd>
              </div>
              <div className="py-3">
                <dt className="text-[12px] text-muted-foreground">API endpoint</dt>
                <dd className="mt-1 break-all text-[12px] font-medium leading-5">
                  {env.apiBaseUrl}
                </dd>
              </div>
            </dl>
          </section>

          <section aria-labelledby="settings-session" className="pb-2">
            <h2 id="settings-session" className="mb-3 text-sm font-semibold">
              Session
            </h2>
            {confirming ? (
              <div className="rounded-xl border border-border bg-card p-4">
                <p className="text-sm font-medium">Sign out of this extension?</p>
                <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
                  You’ll need to sign in again to use it.
                </p>
                {signOutError ? (
                  <Alert variant="destructive" className="mt-3">
                    <AlertDescription>{signOutError}</AlertDescription>
                  </Alert>
                ) : null}
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setConfirming(false)} disabled={pending}>
                    Cancel
                  </Button>
                  <Button variant="destructive" onClick={signOut} disabled={pending}>
                    {pending ? 'Signing out…' : 'Sign out'}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => setConfirming(true)}
              >
                <LogOut aria-hidden="true" />
                Sign out
              </Button>
            )}
          </section>
        </div>
      </main>
      <footer className="flex items-center justify-between border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
        <span>WCM Sales Assistant</span>
        <span>Version {version}</span>
      </footer>
    </div>
  )
}
