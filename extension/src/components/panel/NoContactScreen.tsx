import emptyState from '@/assets/empty-state.png'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { usePanelStore } from '@/stores/panel-store'

export function NoContactScreen() {
  const setView = usePanelStore((s) => s.setView)
  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader onSettings={() => setView('settings')} />
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-full text-center">
          <img src={emptyState} alt="" className="mx-auto mb-2 w-full max-w-[200px]" />
          <p className="text-base font-semibold">Open a contact in GoHighLevel</p>
          <p className="mt-1 text-[13px] text-muted-foreground">
            The assistant appears when a contact record is open.
          </p>
        </div>
      </main>
    </div>
  )
}
