import { Providers } from '@/app/providers'
import { CallMode } from '@/components/panel/CallMode'
import { LoginScreen } from '@/components/panel/LoginScreen'
import { NoAccessScreen } from '@/components/panel/NoAccessScreen'
import { NoContactScreen } from '@/components/panel/NoContactScreen'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { SettingsScreen } from '@/components/panel/SettingsScreen'
import { WrongAccountScreen } from '@/components/panel/WrongAccountScreen'
import { Skeleton } from '@/components/ui/skeleton'
import { useConfigQuery } from '@/hooks/queries'
import { useActiveContact } from '@/hooks/use-active-contact'
import { useAuth } from '@/hooks/use-auth'
import { usePanelStore } from '@/stores/panel-store'

function LoadingScreen() {
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

function Panel() {
  const { user, isLoading } = useAuth()
  const contact = useActiveContact()
  const view = usePanelStore((s) => s.view)
  const configQuery = useConfigQuery(user?.hasExtensionAccess ?? false)

  if (isLoading || user === undefined) return <LoadingScreen />
  if (user === null) return <LoginScreen />
  if (!user.hasExtensionAccess) return <NoAccessScreen />
  if (view === 'settings') return <SettingsScreen />
  if (contact === undefined) return <LoadingScreen />
  if (contact === null) return <NoContactScreen />
  if (configQuery.isPending) return <LoadingScreen />
  if (configQuery.isError) return <LoadingScreen />
  if (contact.locationId !== configQuery.data.ghlLocationId) return <WrongAccountScreen />

  return <CallMode key={contact.contactId} activeContact={contact} />
}

export default function App() {
  return (
    <Providers>
      <Panel />
    </Providers>
  )
}
