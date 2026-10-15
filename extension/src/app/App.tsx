import { lazy, Suspense } from 'react'
import { Providers } from '@/app/providers'
import { CallMode } from '@/components/panel/CallMode'
import { LoginScreen } from '@/components/panel/LoginScreen'
import { NoAccessScreen } from '@/components/panel/NoAccessScreen'
import { NoContactScreen } from '@/components/panel/NoContactScreen'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { SettingsScreen } from '@/components/panel/SettingsScreen'
import { UnsupportedScreen } from '@/components/panel/UnsupportedScreen'
import { WrongAccountScreen } from '@/components/panel/WrongAccountScreen'
import { Skeleton } from '@/components/ui/skeleton'
import { useConfigQuery } from '@/hooks/queries'
import { useActiveTab } from '@/hooks/use-active-tab'
import { useAuth } from '@/hooks/use-auth'
import { asActiveContact } from '@/lib/active-tab'
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

const ResearchMode = lazy(() => import('@/components/research/ResearchMode'))

function Panel() {
  const { user, isLoading } = useAuth()
  const tab = useActiveTab()
  const view = usePanelStore((s) => s.view)
  const configQuery = useConfigQuery(user?.hasExtensionAccess ?? false)

  if (isLoading || user === undefined) return <LoadingScreen />
  if (user === null) return <LoginScreen />
  if (!user.hasExtensionAccess) return <NoAccessScreen />
  if (view === 'settings') return <SettingsScreen user={user} />
  if (tab === undefined) return <LoadingScreen />
  if (tab === null || tab.kind === 'unsupported') return <UnsupportedScreen />
  if (tab.kind === 'ghl_other') return <NoContactScreen />
  if (tab.kind === 'website') {
    return (
      <Suspense fallback={<LoadingScreen />}>
        <ResearchMode key={tab.domain} tab={tab} />
      </Suspense>
    )
  }
  const contact = asActiveContact(tab)
  if (!contact) return <NoContactScreen />
  if (configQuery.isPending) return <LoadingScreen />
  if (configQuery.isError) return <LoadingScreen />
  if (contact.locationId !== configQuery.data.ghlLocationId) return <WrongAccountScreen />

  const callerFirstName = user.fullName.split(' ')[0] ?? ''
  return (
    <CallMode
      key={contact.contactId}
      activeContact={contact}
      callerFirstName={callerFirstName}
      bookingWidgetUrl={configQuery.data.bookingWidgetUrl}
    />
  )
}

export default function App() {
  return (
    <Providers>
      <Panel />
    </Providers>
  )
}
