import { Providers } from '@/app/providers'
import { NoContactScreen } from '@/components/panel/NoContactScreen'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { useActiveContact } from '@/hooks/use-active-contact'

function Panel() {
  const contact = useActiveContact()

  if (contact === undefined) {
    return (
      <div className="flex min-h-screen flex-col">
        <PanelHeader />
        <main className="flex flex-1 flex-col gap-2 p-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </main>
      </div>
    )
  }

  if (contact === null) return <NoContactScreen />

  return (
    <div className="flex min-h-screen flex-col">
      <PanelHeader />
      <main className="flex-1 p-3">
        <p className="text-xs text-muted-foreground">
          locationId={contact.locationId} contactId={contact.contactId}
        </p>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Providers>
      <Panel />
    </Providers>
  )
}
