import emptyState from '@/assets/empty-state.png'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { usePanelStore } from '@/stores/panel-store'

export function UnsupportedScreen() {
  const setView = usePanelStore((s) => s.setView)
  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader onSettings={() => setView('settings')} />
      <main className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center">
        <img src={emptyState} alt="" className="mb-2 w-full max-w-[200px]" />
        <p className="text-lg font-semibold">Open a clinic website or a GHL contact</p>
        <p className="text-[14px] text-muted-foreground">
          Research Mode works on any website. Call Mode appears on a GoHighLevel contact record.
        </p>
      </main>
    </div>
  )
}
