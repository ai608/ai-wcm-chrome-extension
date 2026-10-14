import { Providers } from '@/app/providers'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Button } from '@/components/ui/button'

export default function App() {
  return (
    <Providers>
      <div className="flex min-h-screen flex-col">
        <PanelHeader />
        <main className="flex flex-1 flex-col items-start gap-2 p-3">
          <Button>Hello</Button>
        </main>
      </div>
    </Providers>
  )
}
