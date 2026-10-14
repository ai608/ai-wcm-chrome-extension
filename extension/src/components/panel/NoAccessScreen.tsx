import { PanelHeader } from '@/components/panel/PanelHeader'
import { Card, CardContent } from '@/components/ui/card'

export function NoAccessScreen() {
  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader />
      <main className="flex flex-1 items-center justify-center p-4">
        <Card className="w-full">
          <CardContent className="pt-4 text-center">
            <p className="text-sm font-medium">No extension access</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Ask an admin to grant Chrome Extension access.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
