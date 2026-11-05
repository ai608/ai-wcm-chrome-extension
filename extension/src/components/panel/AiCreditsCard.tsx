import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAiUsage } from '@/hooks/ai-usage'
import type { AiUsage } from '@/lib/api/types'
import { cn } from '@/lib/utils'

/** Under this share of the bought credits left, the balance is shown as running low. */
const LOW_SHARE = 0.2

const usd = (v: number | null | undefined) => (v == null ? '-' : `$${v.toFixed(2)}`)

function Row({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-[12px] text-muted-foreground">{label}</dt>
      <dd className="text-[12px] font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function Balance({ account }: Readonly<{ account: NonNullable<AiUsage['account']> }>) {
  const share = account.creditsUsd > 0 ? account.remainingUsd / account.creditsUsd : 0
  const low = share < LOW_SHARE
  const used = Math.min(100, Math.max(0, 100 - share * 100))
  return (
    <div className="py-3">
      <p className="flex items-baseline gap-2">
        <span className={cn('text-xl font-semibold tabular-nums', low && 'text-destructive')}>
          {usd(account.remainingUsd)}
        </span>
        <span className="text-[12px] text-muted-foreground">left</span>
        {low ? <span className="text-[12px] font-medium text-destructive">Running low</span> : null}
      </p>
      <div
        role="progressbar"
        aria-label="OpenRouter credits used"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(used)}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn('h-full rounded-full', low ? 'bg-destructive' : 'bg-primary')}
          style={{ width: `${used}%` }}
        />
      </div>
      <p className="mt-1.5 text-[12px] text-muted-foreground tabular-nums">
        {usd(account.usedUsd)} used of {usd(account.creditsUsd)} bought. This is the whole
        OpenRouter account, so it also counts other keys and apps.
      </p>
    </div>
  )
}

function Body({ data }: Readonly<{ data: AiUsage }>) {
  const t = data.tracked
  return (
    <div className="divide-y divide-border rounded-xl border border-border bg-card px-4">
      {data.account ? (
        <Balance account={data.account} />
      ) : (
        <p className="py-3 text-[12px] text-destructive">
          Could not read the account balance ({data.errors.account ?? 'error'}).
        </p>
      )}
      {data.key ? (
        <dl>
          <Row label="All users, all time" value={usd(data.key.usedUsd)} />
          <Row label="Today" value={usd(data.key.todayUsd)} />
          <Row label="Last 7 days" value={usd(data.key.weekUsd)} />
          <Row label="Last 30 days" value={usd(data.key.monthUsd)} />
        </dl>
      ) : (
        <p className="py-3 text-[12px] text-destructive">
          Could not read this key’s usage ({data.errors.key ?? 'error'}).
        </p>
      )}
      <p className="py-2.5 text-[12px] leading-5 text-muted-foreground tabular-nums">
        Tracked by the app: audits {usd(t.auditsUsd)} · AI visibility {usd(t.aiVisibilityUsd)} ·{' '}
        {t.users} {t.users === 1 ? 'user' : 'users'}. Only spend since tracking began is split this
        way.
      </p>
    </div>
  )
}

/** AI spend of all users. Rendered for owners and admins only (see SettingsScreen). */
export function AiCreditsCard() {
  const { data, error, isPending, refresh, refreshing } = useAiUsage(true)
  let content: ReactNode
  if (isPending) {
    content = <Skeleton className="h-40 w-full rounded-xl" />
  } else if (error || !data) {
    content = (
      <Alert variant="destructive">
        <AlertDescription>
          {error instanceof Error ? error.message : 'Could not read AI credits.'}
        </AlertDescription>
      </Alert>
    )
  } else if (data.configured) {
    content = <Body data={data} />
  } else {
    content = (
      <p className="rounded-xl border border-border bg-card px-4 py-3 text-[12px] text-muted-foreground">
        OpenRouter is not set up on the server.
      </p>
    )
  }
  return (
    <section aria-labelledby="settings-ai-credits">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="settings-ai-credits" className="text-base font-semibold leading-6">
          AI credits
        </h2>
        <Button
          size="xs"
          variant="ghost"
          onClick={refresh}
          disabled={refreshing || isPending}
          aria-label="Refresh AI credits"
        >
          <RefreshCw aria-hidden="true" className={cn(refreshing && 'animate-spin')} />
          Refresh
        </Button>
      </div>
      {content}
    </section>
  )
}
