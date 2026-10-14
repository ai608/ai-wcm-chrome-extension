import { Moon, RefreshCw, Settings, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { BusinessTab } from '@/components/research/BusinessTab'
import { ConvertTab } from '@/components/research/ConvertTab'
import { OnPageTab } from '@/components/research/OnPageTab'
import { OverviewTab } from '@/components/research/OverviewTab'
import { ResearchSubTabs } from '@/components/research/ResearchSubTabs'
import { SchemaTab } from '@/components/research/SchemaTab'
import { SiteTab } from '@/components/research/SiteTab'
import { SectionGate } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useLatestAudit, useStartAudit } from '@/hooks/research-queries'
import { useTheme } from '@/hooks/use-theme'
import type { ActiveTab } from '@/lib/active-tab'
import { ApiError } from '@/lib/api/errors'
import type { Audit, SectionKey } from '@/lib/api/research-types'
import { getEnv } from '@/lib/env'
import { lastResearchTabItem } from '@/lib/storage'
import { relativeTime } from '@/lib/time'
import { usePanelStore } from '@/stores/panel-store'

const TABS: { value: string; label: string; section: SectionKey }[] = [
  { value: 'overview', label: 'Overview', section: 'overview' },
  { value: 'business', label: 'Business', section: 'business' },
  { value: 'on_page', label: 'On-Page', section: 'on_page' },
  { value: 'schema', label: 'Schema', section: 'schema' },
  { value: 'site', label: 'Site', section: 'site' },
  { value: 'convert', label: 'Convert', section: 'convert' },
  { value: 'research', label: 'Research', section: 'research' },
]

export function startErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'url_not_allowed') return 'This address can’t be audited.'
    if (err.code === 'invalid_url') return 'That isn’t a valid website address.'
    if (err.code === 'site_unreachable') return 'The site couldn’t be reached.'
    if (err.code === 'quota_exceeded') return 'Provider credit limit reached. Try again later.'
    return err.message
  }
  return 'Couldn’t start the audit.'
}

function Favicon({ domain }: { domain: string }) {
  const [ok, setOk] = useState(true)
  if (!ok) return null
  return (
    <img
      src={`https://${domain}/favicon.ico`}
      alt=""
      referrerPolicy="no-referrer"
      className="size-5 shrink-0 rounded"
      onError={() => setOk(false)}
    />
  )
}

function SiteHeader({
  tab,
  audit,
  onRerun,
}: {
  tab: ActiveTab
  audit: Audit | null | undefined
  onRerun: () => void
}) {
  const pending = usePanelStore((s) => s.pendingConfirm)
  const setPending = usePanelStore((s) => s.setPendingConfirm)
  const setView = usePanelStore((s) => s.setView)
  const { isDark, toggle } = useTheme()
  const domain = tab.domain ?? ''
  const ghost =
    'text-white hover:bg-white/15 hover:text-white dark:text-primary-foreground dark:hover:bg-black/10'
  return (
    <header className="bg-brand-blue px-4 py-4 text-white dark:bg-primary dark:text-primary-foreground">
      <div className="flex items-center gap-3">
        <Favicon domain={domain} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-bold leading-tight">{domain}</p>
          <p className="text-[12px] opacity-80">
            Research Mode{audit ? ` · audited ${relativeTime(audit.createdAt)}` : ''}
          </p>
        </div>
        {audit?.overview ? (
          <span className="shrink-0 rounded-full bg-destructive px-2.5 py-1 text-[12px] font-bold text-white">
            {audit.overview.issueCount} issues + {audit.overview.warningCount} warn
          </span>
        ) : null}
        <Button
          variant="ghost"
          size="icon-sm"
          title={isDark ? 'Light mode' : 'Dark mode'}
          onClick={toggle}
          className={ghost}
        >
          {isDark ? <Sun /> : <Moon />}
        </Button>
        {audit ? (
          <Button
            variant="ghost"
            size="icon-sm"
            title="Re-run audit"
            onClick={() => setPending('rerun')}
            className={ghost}
          >
            <RefreshCw />
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="icon-sm"
          title="Settings"
          onClick={() => setView('settings')}
          className={ghost}
        >
          <Settings />
        </Button>
      </div>
      {pending === 'rerun' ? (
        <div className="mt-3 flex items-center gap-2 text-[13px]">
          <span className="flex-1">Re-run the audit? It uses API credits.</span>
          <Button
            variant="outline"
            size="xs"
            className="text-foreground"
            onClick={() => setPending(null)}
          >
            Cancel
          </Button>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => {
              setPending(null)
              onRerun()
            }}
          >
            Re-run
          </Button>
        </div>
      ) : null}
    </header>
  )
}

function EmptyState({
  domain,
  onRun,
  pending,
  error,
}: {
  domain: string
  onRun: () => void
  pending: boolean
  error: string | null
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <p className="text-base font-semibold">{domain}</p>
      <p className="text-[14px] text-muted-foreground">
        Run a website &amp; local visibility audit for this clinic.
      </p>
      <Button size="lg" onClick={onRun} disabled={pending}>
        {pending ? 'Starting…' : 'Run audit'}
      </Button>
      <p className="text-[12px] text-muted-foreground">
        Uses Firecrawl, PageSpeed and Google data. Takes ~30–90 s.
      </p>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

export default function ResearchMode({ tab }: { tab: ActiveTab }) {
  const domain = tab.domain ?? ''
  const { audit, query, timedOut } = useLatestAudit(domain)
  const start = useStartAudit(domain)
  const researchTab = usePanelStore((s) => s.researchTab)
  const setResearchTab = usePanelStore((s) => s.setResearchTab)

  useEffect(() => {
    lastResearchTabItem.getValue().then(setResearchTab)
  }, [setResearchTab])

  const url = `${tab.origin ?? ''}${(() => {
    try {
      return new URL(tab.url).pathname
    } catch {
      return '/'
    }
  })()}`
  const run = (force?: boolean) => start.mutate({ url, force })
  const env = getEnv()

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <SiteHeader tab={tab} audit={audit} onRerun={() => run(true)} />
      {query.isPending ? (
        <div className="p-4">
          <Skeleton className="h-24 w-full" />
        </div>
      ) : query.isError ? (
        <div className="p-4">
          <Alert variant="destructive">
            <AlertDescription>Couldn’t load audit data.</AlertDescription>
          </Alert>
        </div>
      ) : !audit ? (
        <EmptyState
          domain={domain}
          onRun={() => run()}
          pending={start.isPending}
          error={start.isError ? startErrorMessage(start.error) : null}
        />
      ) : (
        <Tabs
          value={researchTab}
          onValueChange={(v) => {
            setResearchTab(String(v))
            lastResearchTabItem.setValue(String(v)).catch(() => {})
          }}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="border-b border-border bg-muted/60 px-2">
            <TabsList variant="line" className="h-auto w-full flex-wrap justify-center gap-x-1 p-0">
              {TABS.map((t) => (
                <TabsTrigger
                  key={t.value}
                  value={t.value}
                  className="h-9 flex-none px-2.5 text-[14px] font-semibold"
                >
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {timedOut ? (
              <Alert className="mb-3">
                <AlertDescription className="flex items-center gap-2">
                  <span className="flex-1">Still running…</span>
                  <Button size="xs" variant="outline" onClick={() => run(true)}>
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}
            {audit.status === 'failed' ? (
              <Alert variant="destructive" className="mb-3">
                <AlertDescription>{audit.error ?? 'The audit failed.'}</AlertDescription>
              </Alert>
            ) : null}
            {TABS.map((t) => (
              <TabsContent key={t.value} value={t.value}>
                {t.value === 'overview' ? (
                  audit.sectionState.overview === 'failed' ? (
                    <SectionGate audit={audit} section="overview">
                      {null}
                    </SectionGate>
                  ) : (
                    <OverviewTab audit={audit} />
                  )
                ) : (
                  <SectionGate audit={audit} section={t.section}>
                    {t.value === 'business' && audit.business ? (
                      <BusinessTab business={audit.business} />
                    ) : t.value === 'on_page' && audit.onPage ? (
                      <OnPageTab audit={audit} onPage={audit.onPage} />
                    ) : t.value === 'schema' && audit.schema ? (
                      <SchemaTab audit={audit} schema={audit.schema} />
                    ) : t.value === 'site' && audit.site ? (
                      <SiteTab audit={audit} site={audit.site} />
                    ) : t.value === 'convert' && audit.convert ? (
                      <ConvertTab convert={audit.convert} />
                    ) : t.value === 'research' ? (
                      <ResearchSubTabs audit={audit} />
                    ) : null}
                  </SectionGate>
                )}
              </TabsContent>
            ))}
          </div>
        </Tabs>
      )}
      <footer className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[12px] text-muted-foreground">
        <span>Research Mode</span>
        <span>{env.apiMock ? 'mock' : env.apiBaseUrl}</span>
      </footer>
    </div>
  )
}
