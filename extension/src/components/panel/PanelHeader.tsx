export function PanelHeader() {
  return (
    <header className="flex items-center gap-2 border-b border-border bg-brand-dark px-3 py-2">
      <img src="/brand/logo-head-light.webp" alt="WCM" className="h-6 w-auto" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-white">WCM Sales Assistant</p>
      </div>
    </header>
  )
}
