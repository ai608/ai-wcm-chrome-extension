import { Moon, RefreshCw, Settings, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/use-theme'

interface PanelHeaderProps {
  mode?: string
  onRefresh?: () => void
  refreshing?: boolean
  onSettings?: () => void
}

export function PanelHeader({
  mode = 'Call Mode',
  onRefresh,
  refreshing,
  onSettings,
}: PanelHeaderProps) {
  const { isDark, toggle } = useTheme()
  return (
    <header className="flex items-center gap-2 border-b border-border bg-brand-blue px-4 py-5 dark:bg-primary">
      <span className="mr-auto text-xl font-semibold leading-tight text-white">{mode}</span>
      <Button
        variant="ghost"
        size="icon-sm"
        title={isDark ? 'Light mode' : 'Dark mode'}
        onClick={toggle}
        className="text-white hover:bg-white/10 hover:text-white"
      >
        {isDark ? <Sun /> : <Moon />}
      </Button>
      {onRefresh ? (
        <Button
          variant="ghost"
          size="icon-sm"
          title="Refresh"
          onClick={onRefresh}
          disabled={refreshing}
          className="text-white hover:bg-white/10 hover:text-white"
        >
          <RefreshCw />
        </Button>
      ) : null}
      {onSettings ? (
        <Button
          variant="ghost"
          size="icon-sm"
          title="Settings"
          onClick={onSettings}
          className="text-white hover:bg-white/10 hover:text-white"
        >
          <Settings />
        </Button>
      ) : null}
    </header>
  )
}
