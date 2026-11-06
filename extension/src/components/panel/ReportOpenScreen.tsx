import { useEffect, useState } from 'react'
import emptyState from '@/assets/empty-state.webp'
import { PanelHeader } from '@/components/panel/PanelHeader'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import { type ActiveTab, REPORT_PRINT_TYPE } from '@/lib/active-tab'
import { cn } from '@/lib/utils'
import { usePanelStore } from '@/stores/panel-store'

export function ReportOpenScreen({ tab }: { tab: ActiveTab }) {
  const setView = usePanelStore((s) => s.setView)
  const auditId = tab.auditId ?? ''
  const [downloading, setDownloading] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'run' | 'done'>('idle')

  useEffect(() => {
    if (!downloading) return
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() =>
        setPhase((current) => (current === 'done' ? current : 'run')),
      )
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [downloading])

  async function downloadPdf() {
    console.info('[report-panel] pdf', { auditId, tabId: tab.tabId })
    setPhase('idle')
    setDownloading(true)
    let saved = false
    try {
      const res = (await browser.runtime.sendMessage({
        type: REPORT_PRINT_TYPE,
        auditId,
      })) as { ok?: boolean } | undefined
      saved = !!res?.ok
      if (!saved) {
        console.error('[report-panel] pdf failed', { auditId, tabId: tab.tabId })
        toast('Couldn’t download the PDF')
      }
    } catch (err) {
      console.error('[report-panel] pdf failed', { auditId, tabId: tab.tabId, err })
      toast('Couldn’t download the PDF')
    } finally {
      if (saved) {
        setPhase('done')
        await new Promise((resolve) => setTimeout(resolve, 240))
      }
      setDownloading(false)
      setPhase('idle')
    }
  }

  async function copyAudit() {
    try {
      await navigator.clipboard.writeText(auditId)
      toast('Copied')
    } catch (err) {
      console.error('[report-panel] copy failed', { auditId, err })
      toast('Couldn’t copy')
    }
  }

  async function closeReport() {
    console.info('[report-panel] close', { auditId, tabId: tab.tabId })
    try {
      await browser.tabs.remove(tab.tabId)
    } catch (err) {
      console.error('[report-panel] close failed', { auditId, tabId: tab.tabId, err })
      toast('Couldn’t close the report')
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <PanelHeader mode="Report" onSettings={() => setView('settings')} />
      <main className="flex flex-1 items-center justify-center px-6">
        <div className="flex w-full max-w-[280px] flex-col items-center">
          <img src={emptyState} alt="" className="w-full max-w-[200px]" />
          <h2 className="mt-4 text-lg font-semibold">Report is ready</h2>
          <div className="mt-4 flex w-full flex-col gap-2">
            <button
              type="button"
              disabled={downloading}
              aria-busy={downloading}
              onClick={() => void downloadPdf()}
              className={cn(
                'relative inline-flex h-8 w-full items-center justify-center overflow-hidden rounded-lg border text-sm font-semibold text-white outline-none',
                'transition-[background-color,border-color] duration-500 ease-in-out',
                'focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none',
                downloading ? 'border-primary bg-white' : 'border-transparent bg-primary',
              )}
            >
              {downloading ? (
                <span
                  aria-hidden
                  className={cn(
                    'report-pdf-fill absolute inset-0 bg-primary',
                    phase === 'run' && 'is-run',
                    phase === 'done' && 'is-done',
                  )}
                />
              ) : null}
              <span className="relative text-white">
                {downloading ? 'Downloading the PDF' : 'Download as PDF'}
              </span>
            </button>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" className="w-full" onClick={() => void copyAudit()}>
                Copy link
              </Button>
              <Button variant="outline" className="w-full" onClick={() => void closeReport()}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
