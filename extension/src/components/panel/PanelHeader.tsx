import { RefreshCw, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PanelHeaderProps {
  onRefresh?: () => void
  refreshing?: boolean
  onSettings?: () => void
}

export function PanelHeader({ onRefresh, refreshing, onSettings }: PanelHeaderProps) {
  return (
    <header className="flex items-center gap-2 border-b border-border bg-brand-dark px-3 py-2">
      <img src="/brand/logo-head-light.webp" alt="WCM" className="h-6 w-auto" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-white">WCM Sales Assistant</p>
        <p className="text-[11px] text-white/70">Call Mode</p>
      </div>
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
