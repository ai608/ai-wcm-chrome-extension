import { useState } from 'react'
import { Block, Chip, FilterChips, Row, StatBox } from '@/components/research/shared'
import type { OnPageIssue, OnPagePage, OnPageSection, Severity } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

const TONE: Record<Severity, 'bad' | 'warn' | 'default'> = {
  critical: 'bad',
  high: 'bad',
  medium: 'warn',
  low: 'default',
}
const RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 }

function pathOf(url: string): string {
  try {
    const u = new URL(url)
    return `${u.pathname}${u.search}` || '/'
  } catch {
    return url
  }
}

function scoreTone(score: number): 'good' | 'bad' | undefined {
  if (score >= 80) return 'good'
  return score < 60 ? 'bad' : undefined
}

function Fix({ fix }: { fix: NonNullable<OnPageSection['summary']>['topFixes'][number] }) {
  return (
    <li className="rounded-lg border border-border p-3 text-[13px]">
      <div className="flex items-start gap-2">
        <Chip tone={TONE[fix.severity]}>{fix.severity}</Chip>
        <p className="flex-1 font-medium">{fix.title}</p>
        {fix.count > 1 ? (
          <span className="text-[12px] text-muted-foreground">{fix.count} pages</span>
        ) : null}
      </div>
      <p className="mt-1 text-muted-foreground">{fix.detail}</p>
      {fix.pages.length ? (
        <p className="mt-1 break-all text-[12px] text-muted-foreground">
          {fix.pages.slice(0, 3).map(pathOf).join(' · ')}
          {fix.pages.length > 3 ? ' …' : ''}
        </p>
      ) : null}
    </li>
  )
}

export function Summary({ onPage }: { onPage: OnPageSection }) {
  const s = onPage.summary
  if (!s)
    return <p className="text-[13px] text-muted-foreground">No per-page checks for this audit.</p>
  const trust = onPage.trust
  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <StatBox label="On-page score" value={`${s.score} / 100`} tone={scoreTone(s.score)} />
        <StatBox label="Critical" value={s.critical} tone={s.critical ? 'bad' : 'good'} />
        <StatBox label="High" value={s.high} tone={s.high ? 'bad' : 'good'} />
        <StatBox label="Medium" value={s.medium} />
      </div>
      <Block title="Top fixes">
        {s.topFixes.length ? (
          <ul className="flex flex-col gap-2">
            {s.topFixes.map((f) => (
              <Fix key={f.key} fix={f} />
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted-foreground">No important on-page problems found.</p>
        )}
      </Block>
      {trust ? (
        <Block title="Patient trust signals">
          <Row label="Provider credentials" status={trust.credentialsPages.length ? 'ok' : 'warn'}>
            {trust.credentialsPages.length ? 'Shown' : 'Not found'}
          </Row>
          <Row
            label="Reviewed or dated"
            status={trust.reviewedByPages.length || trust.datedPages.length ? 'ok' : 'warn'}
          >
            {trust.reviewedByPages.length || trust.datedPages.length ? 'Found' : 'Not found'}
          </Row>
          <Row label="Health sources" status={trust.referenceLinks ? 'ok' : 'warn'}>
            {trust.referenceLinks ? `${trust.referenceLinks} links` : 'None linked'}
          </Row>
          <Row label="Results disclaimer" status={trust.disclaimerPages.length ? 'ok' : 'warn'}>
            {trust.disclaimerPages.length ? 'Found' : 'Not found'}
          </Row>
        </Block>
      ) : null}
      <Block title="Links, images and local">
        <Row
          label="Link text"
          status={onPage.links.genericAnchorCount || onPage.links.emptyAnchorCount ? 'warn' : 'ok'}
        >
          {onPage.links.genericAnchorCount ?? 0} vague, {onPage.links.emptyAnchorCount ?? 0} empty,{' '}
          {onPage.links.notCrawlableCount ?? 0} not followable
        </Row>
        <Row
          label="Images"
          status={onPage.images.firstImageLazy || onPage.images.badAlt ? 'warn' : 'ok'}
        >
          {onPage.images.firstImageLazy ? 'First big image loads late. ' : ''}
          {onPage.images.badAlt ?? 0} with unhelpful alt text, {onPage.images.badNames ?? 0} with
          meaningless file names
        </Row>
        {onPage.local ? (
          <Row
            label="Local"
            status={onPage.local.mapEmbed && onPage.local.hoursText ? 'ok' : 'warn'}
          >
            Map {onPage.local.mapEmbed ? 'shown' : 'missing'}, hours{' '}
            {onPage.local.hoursText ? 'written out' : 'not written out'}
          </Row>
        ) : null}
      </Block>
      {onPage.orphans?.length ? (
        <Block title="Service pages nobody links to">
          <ul className="flex flex-col gap-1 text-[13px] text-muted-foreground">
            {onPage.orphans.map((u) => (
              <li key={u} className="break-all">
                {pathOf(u)}
              </li>
            ))}
          </ul>
        </Block>
      ) : null}
    </div>
  )
}

type Filter = 'all' | 'issues' | 'serious'

function worst(p: OnPagePage): number {
  return p.issues.length ? Math.min(...p.issues.map((i) => RANK[i.severity])) : 4
}

function IssueLine({ issue }: { issue: OnPageIssue }) {
  return (
    <li className="flex items-start gap-2 text-[13px]">
      <Chip tone={TONE[issue.severity]}>{issue.severity}</Chip>
      <span className="flex-1">
        <span className="font-medium">{issue.title}</span>
        <span className="block text-muted-foreground">{issue.detail}</span>
      </span>
    </li>
  )
}

function PageRow({ page }: { page: OnPagePage }) {
  const top = worst(page)
  return (
    <details className="group rounded-lg border border-border p-3">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden="true"
          className={cn(
            'size-2 shrink-0 rounded-full',
            top <= 1 ? 'bg-destructive' : top === 2 ? 'bg-accent-wcm' : 'bg-success',
          )}
        />
        <span className="min-w-0 flex-1 break-all font-medium">{pathOf(page.url)}</span>
        <Chip>{page.kind.replace('_', ' ')}</Chip>
        <span className="text-[12px] text-muted-foreground">
          {page.issues.length
            ? `${page.issues.length} issue${page.issues.length > 1 ? 's' : ''}`
            : 'OK'}
        </span>
      </summary>
      <div className="mt-2">
        <Row label="Title">{page.title || 'Missing'}</Row>
        <Row label="Main heading">{page.h1 || 'Missing'}</Row>
        <Row label="Words">{page.wordCount}</Row>
        <Row label="Canonical">{page.canonical.status}</Row>
        {page.issues.length ? (
          <ul className="mt-2 flex flex-col gap-2">
            {page.issues.map((i) => (
              <IssueLine key={`${i.key}-${i.url}`} issue={i} />
            ))}
          </ul>
        ) : null}
      </div>
    </details>
  )
}

export function Pages({ onPage }: { onPage: OnPageSection }) {
  const [filter, setFilter] = useState<Filter>('issues')
  const pages = onPage.pages ?? []
  if (!pages.length) {
    return <p className="text-[13px] text-muted-foreground">No per-page checks for this audit.</p>
  }
  const shown = pages
    .filter((p) =>
      filter === 'all' ? true : filter === 'issues' ? p.issues.length > 0 : worst(p) <= 1,
    )
    .sort((a, b) => worst(a) - worst(b) || b.issues.length - a.issues.length)
  return (
    <div className="flex flex-col gap-3">
      <FilterChips
        value={filter}
        onChange={setFilter}
        items={[
          { value: 'issues', label: `With issues ${pages.filter((p) => p.issues.length).length}` },
          { value: 'serious', label: `Serious ${pages.filter((p) => worst(p) <= 1).length}` },
          { value: 'all', label: `All ${pages.length}` },
        ]}
      />
      {shown.length ? (
        <div className="flex flex-col gap-2">
          {shown.map((p) => (
            <PageRow key={p.url} page={p} />
          ))}
        </div>
      ) : (
        <p className="text-[13px] text-muted-foreground">No pages match.</p>
      )}
    </div>
  )
}
