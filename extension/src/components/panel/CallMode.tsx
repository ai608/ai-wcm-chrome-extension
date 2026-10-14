import { lazy, Suspense, useEffect } from 'react'
import { HistoryTab } from '@/components/history/HistoryTab'
import { ContactHeader } from '@/components/panel/ContactHeader'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { StatusBanner } from '@/components/panel/StatusBanner'
import { ScriptTab } from '@/components/script/ScriptTab'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useRefreshContact } from '@/hooks/queries'
import { useScriptState } from '@/hooks/use-script-state'
import { getEnv } from '@/lib/env'
import type { ActiveContact } from '@/lib/storage'
import { lastTabItem } from '@/lib/storage'
import { useAutosaveStore } from '@/stores/autosave-store'
import { usePanelStore } from '@/stores/panel-store'

const ResearchTab = lazy(() => import('@/components/research/ResearchTab'))

function envLabel(): string {
  const env = getEnv()
  return env.apiMock ? 'mock' : env.apiBaseUrl
}

export function CallMode({
  activeContact,
  callerFirstName,
  bookingWidgetUrl,
}: {
  activeContact: ActiveContact
  callerFirstName: string
  bookingWidgetUrl: string
}) {
  const { contactId } = activeContact
  const activeTab = usePanelStore((s) => s.activeTab)
  const setActiveTab = usePanelStore((s) => s.setActiveTab)
  const setView = usePanelStore((s) => s.setView)
  const pendingConfirm = usePanelStore((s) => s.pendingConfirm)
  const setPendingConfirm = usePanelStore((s) => s.setPendingConfirm)
  const refreshContact = useRefreshContact()
  const scriptState = useScriptState(contactId)

  useEffect(() => {
    lastTabItem.getValue().then(setActiveTab)
  }, [setActiveTab])

  useEffect(() => {
    const flush = () => useAutosaveStore.getState().flush(contactId)
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') useAutosaveStore.getState().flushAll()
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', flush)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', flush)
      flush()
    }
  }, [contactId])

  function changeTab(v: string) {
    if (v !== 'script' && v !== 'history' && v !== 'research') return
    setActiveTab(v)
    lastTabItem.setValue(v).catch(() => {})
  }

  const autosaveError = useAutosaveStore((s) => s.lastError[contactId] ?? null)

  const bannerError = scriptState.contextError ?? autosaveError ?? null

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PanelHeader
        onRefresh={() => refreshContact(contactId)}
        onSettings={() => setView('settings')}
      />
      {scriptState.context ? (
        <ContactHeader
          contact={scriptState.context.contact}
          definitionVersion={scriptState.definition?.version}
          script={scriptState.script}
          onRegenerate={() => setPendingConfirm('regenerate')}
        />
      ) : (
        <div className="border-b border-border px-3 py-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-1 h-3 w-1/2" />
        </div>
      )}
      {pendingConfirm === 'regenerate' ? (
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-[13px]">
          <span className="flex-1">Regenerate personalized lines?</span>
          <Button variant="outline" size="xs" onClick={() => setPendingConfirm(null)}>
            Cancel
          </Button>
          <Button
            size="xs"
            onClick={() => {
              setPendingConfirm(null)
              scriptState.startRegenerate()
            }}
          >
            Regenerate
          </Button>
        </div>
      ) : null}
      <StatusBanner
        error={bannerError}
        onRetry={() => {
          if (scriptState.contextError) refreshContact(contactId)
          else useAutosaveStore.getState().flush(contactId)
        }}
      />
      <Tabs value={activeTab} onValueChange={changeTab} className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border px-4 py-2.5">
          <TabsList className="w-full">
            <TabsTrigger value="script">Script</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="research">Research</TabsTrigger>
          </TabsList>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-4 py-3">
            <TabsContent value="script">
              <ScriptTab
                contactId={contactId}
                callerFirstName={callerFirstName}
                bookingWidgetUrl={bookingWidgetUrl}
                state={scriptState}
              />
            </TabsContent>
            <TabsContent value="history">
              <HistoryTab contactId={contactId} />
            </TabsContent>
            <TabsContent value="research">
              <Suspense fallback={<Skeleton className="h-32 w-full" />}>
                <ResearchTab contactId={contactId} />
              </Suspense>
            </TabsContent>
          </div>
        </div>
      </Tabs>
      <footer className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[12px] text-muted-foreground">
        <span>Call Mode</span>
        <span>{envLabel()}</span>
      </footer>
    </div>
  )
}
