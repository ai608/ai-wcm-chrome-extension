import { PanelHeader } from '@/components/panel/PanelHeader'
import { Card, CardContent } from '@/components/ui/card'
import { usePanelStore } from '@/stores/panel-store'

export function WrongAccountScreen() {
  const setView = usePanelStore((s) => s.setView)
  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader onSettings={() => setView('settings')} />
      <main className="flex flex-1 items-center justify-center p-4">
        <Card className="w-full">
          <CardContent className="pt-4 text-center">
            <p className="text-sm font-medium">Wrong GHL account</p>
            <p className="mt-1 text-[13px] text-muted-foreground">
              This isn&apos;t the WCM Sales account. The assistant only works there.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
