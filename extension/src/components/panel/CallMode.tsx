import { useEffect } from 'react'
import { ContactHeader } from '@/components/panel/ContactHeader'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { StatusBanner } from '@/components/panel/StatusBanner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  useContactContextQuery,
  usePersonalizedScriptQuery,
  useRefreshContact,
  useRegenerateScriptMutation,
} from '@/hooks/queries'
import { getEnv } from '@/lib/env'
import type { ActiveContact } from '@/lib/storage'
import { lastTabItem } from '@/lib/storage'
import { usePanelStore } from '@/stores/panel-store'

function envLabel(): string {
  const env = getEnv()
  return env.apiMock ? 'mock' : env.apiBaseUrl
}

export function CallMode({ activeContact }: { activeContact: ActiveContact }) {
  const { contactId } = activeContact
  const activeTab = usePanelStore((s) => s.activeTab)
  const setActiveTab = usePanelStore((s) => s.setActiveTab)
  const setView = usePanelStore((s) => s.setView)
  const pendingConfirm = usePanelStore((s) => s.pendingConfirm)
  const setPendingConfirm = usePanelStore((s) => s.setPendingConfirm)
  const refreshContact = useRefreshContact()
  const regenerate = useRegenerateScriptMutation(contactId)

  useEffect(() => {
    lastTabItem.getValue().then(setActiveTab)
  }, [setActiveTab])

  function changeTab(v: string) {
    if (v !== 'script' && v !== 'history' && v !== 'research') return
    setActiveTab(v)
    lastTabItem.setValue(v).catch(() => {})
  }

  const contextQuery = useContactContextQuery(contactId)
  const scriptQuery = usePersonalizedScriptQuery(contactId, false)

  const bannerError = contextQuery.error ?? scriptQuery.error ?? null

  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader
        onRefresh={() => refreshContact(contactId)}
        onSettings={() => setView('settings')}
      />
      {contextQuery.data ? (
        <ContactHeader
          contact={contextQuery.data.contact}
          definitionVersion={undefined}
          script={scriptQuery.data}
          onRegenerate={() => setPendingConfirm('regenerate')}
        />
      ) : (
        <div className="border-b border-border px-3 py-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-1 h-3 w-1/2" />
        </div>
      )}
      {pendingConfirm === 'regenerate' ? (
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-xs">
          <span className="flex-1">Regenerate personalized lines?</span>
          <Button variant="outline" size="xs" onClick={() => setPendingConfirm(null)}>
            Cancel
          </Button>
          <Button
            size="xs"
            onClick={() => {
              setPendingConfirm(null)
              regenerate.mutate()
            }}
          >
            Regenerate
          </Button>
        </div>
      ) : null}
      <StatusBanner error={bannerError} onRetry={() => refreshContact(contactId)} />
      <Tabs value={activeTab} onValueChange={changeTab} className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border px-3 pt-2">
          <TabsList>
            <TabsTrigger value="script">Script</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="research">Research</TabsTrigger>
          </TabsList>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-3">
            <TabsContent value="script">
              {contextQuery.isPending ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : contextQuery.isError ? (
                <Alert variant="destructive">
                  <AlertDescription>Contact not found in GHL</AlertDescription>
                </Alert>
              ) : (
                <p className="text-xs text-muted-foreground">Script coming soon.</p>
              )}
            </TabsContent>
            <TabsContent value="history">
              <p className="text-xs text-muted-foreground">History coming soon.</p>
            </TabsContent>
            <TabsContent value="research">
              <p className="text-xs text-muted-foreground">Research coming soon.</p>
            </TabsContent>
          </div>
        </ScrollArea>
      </Tabs>
      <footer className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[11px] text-muted-foreground">
        <span>Call Mode</span>
        <span>{envLabel()}</span>
      </footer>
    </div>
  )
}
