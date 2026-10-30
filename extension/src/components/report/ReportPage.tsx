import { CheckIcon, MinusIcon, XIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { CompetitorList } from '@/components/research/ResearchSubTabs'
import { Chip, gradeClass } from '@/components/research/shared'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toast'
import { useReport } from '@/hooks/research-queries'
import { useAuth } from '@/hooks/use-auth'
import {
  type CategoryKey,
  type CheckStatus,
  isLegacyOverview,
  type Report,
} from '@/lib/api/research-types'
import { formatDateTime } from '@/lib/time'
import { cn } from '@/lib/utils'

const EXACT = '[print-color-adjust:exact] [-webkit-print-color-adjust:exact]'

const FIX: Record<CategoryKey, [string, string]> = {
  google_business_profile: [
    'Fix how Google sees the clinic.',
    'Claim and complete the profile, pick the right categories, keep the name, address and phone identical everywhere and link the profile from the site.',
  ],
  reviews: [
    'Turn happy patients into reviews.',
    'Ask every satisfied patient for a Google review with one tap and put the review link on the website.',
  ],
  service_pages: [
    'Build a page for every treatment.',
    'One page per treatment that answers what it is, who it is for, how it works, results, recovery, pricing and common questions.',
  ],
  service_area: [
    'Build a page for every town they serve.',
    'A locations hub plus a page for each city, so patients nearby land on a page written for their search.',
  ],
  getting_the_call: [
    'Make it easy to book.',
    'Put the phone number in the header, add online booking and a contact form, and show the next step on every page.',
  ],
  site_fundamentals: [
    'Fix the technical basics.',
    'Page titles, descriptions, headings, local business markup and a fast mobile site that Google and phones both reward.',
  ],
  content_and_proof: [
    'Show real results.',
    'Before-and-after galleries, patient stories and provider credentials on the pages where patients decide.',
  ],
  supporting_content: [
    'Publish helpful content on a schedule.',
    'Posts that answer the questions patients search before booking, linked to the treatment pages.',
  ],
  social_and_video: [
    'Show the clinic on social and video.',
    'Link active social profiles and add short videos from the providers.',
  ],
}

function Section({
  title,
  kicker,
  children,
}: {
  title: string
  kicker?: string
  children: ReactNode
}) {
  return (
    <section className="break-inside-avoid rounded-xl border border-border bg-card p-5 print:break-inside-avoid">
      <div className="mb-3 border-b border-primary/20 pb-2">
        {kicker ? (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-accent-wcm">
            {kicker}
          </p>
        ) : null}
        <h2 className="text-[16px] font-semibold text-primary">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function Tile({ value, label, tone }: { value: ReactNode; label: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="flex-1 break-inside-avoid rounded-lg border border-border px-3 py-2.5 text-center print:break-inside-avoid">
      <p
        className={cn(
          'text-2xl font-semibold leading-tight',
          tone === 'good' && 'text-success',
          tone === 'bad' && 'text-destructive',
        )}
      >
        {value}
      </p>
      <p className="text-[12px] text-muted-foreground">{label}</p>
    </div>
  )
}

function Mark({ status }: { status: CheckStatus }) {
  const Icon = status === 'ok' ? CheckIcon : status === 'warn' ? MinusIcon : XIcon
  return (
    <span
      role="img"
      aria-label={status}
      className={cn(
        'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full text-white',
        status === 'ok' ? 'bg-success' : status === 'warn' ? 'bg-accent-wcm' : 'bg-destructive',
        EXACT,
      )}
    >
      <Icon className="size-3" strokeWidth={3} />
    </span>
  )
}

function CheckList({
  items,
}: {
  items: { key: string; label: string; status: CheckStatus; note?: string }[]
}) {
  return (
    <ul className="flex flex-col gap-1.5 text-[13px]">
      {items.map((c) => (
        <li key={c.key} className="flex break-inside-avoid gap-2 print:break-inside-avoid">
          <Mark status={c.status} />
          <span>
            {c.label}
            {c.note ? <span className="text-muted-foreground"> · {c.note}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Meter({ label, value }: { label: string; value: number | null | undefined }) {
  const tone =
    value == null
      ? ''
      : value >= 90
        ? 'bg-success'
        : value >= 50
          ? 'bg-accent-wcm'
          : 'bg-destructive'
  return (
    <div className="flex-1 break-inside-avoid print:break-inside-avoid">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-semibold">{value ?? '-'}</span>
      </div>
      <Progress value={value ?? 0} className="mt-1" indicatorClassName={cn(tone, EXACT)} />
    </div>
  )
}

export function Body({ report }: { report: Report }) {
  const { audit } = report
  const o = audit.overview?.score != null && audit.overview.grade != null ? audit.overview : null
  const legacy = o ? isLegacyOverview(o) : false
  const reasons = o?.provisionalReasons ?? []
  const gbp = audit.business?.gbp
  const site = audit.site
  const r = audit.research
  const speed = audit.onPage?.pagespeed
  const label = (k: CategoryKey) => o?.categories.find((c) => c.key === k)?.label ?? ''
  const fixes = o
    ? [...new Set(o.topIssues.map((i) => i.category))].filter((k) => FIX[k]).slice(0, 4)
    : []
  const found = site?.services.clusters.reduce((n, c) => n + c.found, 0) ?? 0
  return (
    <div className="flex flex-col gap-4 print:block print:space-y-4">
      <header
        className={cn(
          'flex break-inside-avoid items-center gap-3 rounded-xl bg-primary px-5 py-4 text-primary-foreground',
          EXACT,
        )}
      >
        <img src="/brand/logo-head-light.webp" alt="WCM" className="h-8 w-auto" />
        <h1 className="flex-1 text-[18px] font-semibold">Website &amp; Local Visibility Report</h1>
        <div className="text-right text-[13px]">
          <p className="font-medium">{audit.domain}</p>
          <p>{formatDateTime(report.generatedAt)}</p>
        </div>
      </header>

      {o ? (
        <section className="break-inside-avoid rounded-xl border border-border bg-card p-5 print:break-inside-avoid">
          <div className="flex items-center gap-5">
            <div
              className={cn(
                'flex size-24 shrink-0 items-center justify-center rounded-full text-5xl font-bold',
                EXACT,
                gradeClass(o.grade ?? 'F'),
              )}
            >
              {o.grade}
            </div>
            <div>
              <p className="text-[14px] text-muted-foreground">Prepared for {report.preparedFor}</p>
              <p className="text-3xl font-semibold text-primary">Overall score: {o.score} / 100</p>
              {o.provisional ? (
                <p className="text-[12px] text-muted-foreground">
                  {!legacy && reasons.length
                    ? `Provisional: ${reasons.join('; ')}.`
                    : 'Provisional: Google Business Profile not matched; GBP and reviews not scored.'}
                </p>
              ) : null}
            </div>
          </div>
          <p className="mt-4 text-[14px] leading-relaxed">{report.intro}</p>
          <div className="mt-4 flex gap-3">
            {site ? (
              <Tile
                value={found}
                label="Treatment pages found"
                tone={found < 5 ? 'bad' : undefined}
              />
            ) : null}
            {site ? (
              <Tile
                value={site.cities.pagesFound}
                label="City pages"
                tone={site.cities.pagesFound === 0 ? 'bad' : 'good'}
              />
            ) : null}
            <Tile
              value={gbp?.matched && gbp.rating != null ? `${gbp.rating} ★` : '-'}
              label={gbp?.matched ? `${gbp.reviewCount ?? 0} Google reviews` : 'Google reviews'}
            />
            <Tile
              value={speed?.mobilePerformance ?? '-'}
              label="Mobile speed"
              tone={
                speed?.mobilePerformance == null
                  ? undefined
                  : speed.mobilePerformance >= 90
                    ? 'good'
                    : speed.mobilePerformance < 50
                      ? 'bad'
                      : undefined
              }
            />
          </div>
        </section>
      ) : null}

      {o ? (
        <Section title="Where the score comes from">
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 print:grid">
            {[...o.categories]
              .sort((x, y) => Number(x.score == null) - Number(y.score == null))
              .filter((c) => !legacy || c.key !== 'getting_the_call')
              .map((c) =>
                c.score == null ? (
                  <div
                    key={c.key}
                    className="flex items-baseline justify-between gap-3 text-[13px] text-muted-foreground"
                  >
                    <span className="font-medium">{c.label}</span>
                    <span className="shrink-0">Not assessed</span>
                  </div>
                ) : (
                  <div key={c.key} className="break-inside-avoid print:break-inside-avoid">
                    <div className="flex items-baseline justify-between gap-3 text-[13px]">
                      <span className="font-medium">{c.label}</span>
                      <span className="shrink-0 font-semibold">
                        {c.score} / 100 ({c.grade})
                      </span>
                    </div>
                    <Progress
                      value={c.score}
                      className="mt-1 print:border print:border-border"
                      indicatorClassName={cn(
                        c.score >= 80
                          ? 'bg-success'
                          : c.score >= 60
                            ? 'bg-accent-wcm'
                            : 'bg-destructive',
                        EXACT,
                      )}
                    />
                  </div>
                ),
              )}
          </div>
          <p className="mt-3 text-[12px] text-muted-foreground">
            {legacy
              ? 'Home page checks only. Google Business Profile and reviews are not scored yet.'
              : 'Weighted across nine categories. Categories without data are left out of the score.'}
          </p>
        </Section>
      ) : null}

      {o ? (
        <Section title="What’s costing them calls" kicker="The biggest gaps first">
          <ol className="flex flex-col gap-2.5">
            {o.topIssues.map((i, n) => (
              <li
                key={i.title}
                className={cn(
                  'flex break-inside-avoid gap-3 rounded-lg border border-l-4 border-border bg-background px-3 py-2.5 print:break-inside-avoid',
                  n < 3 ? 'border-l-destructive' : 'border-l-accent-wcm',
                )}
              >
                <span
                  className={cn(
                    'flex size-6 shrink-0 items-center justify-center rounded-full text-[12px] font-bold text-white',
                    n < 3 ? 'bg-destructive' : 'bg-accent-wcm',
                    EXACT,
                  )}
                >
                  {n + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold">{i.title}</p>
                  <p className="text-[13px] text-muted-foreground">{i.detail}</p>
                  {label(i.category) ? (
                    <p className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                      {label(i.category)}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}

      {site ? (
        <Section title="Treatment pages" kicker="What patients can find">
          {site.pagesCrawled <= 1 ? (
            <p className="mb-2 text-[12px] text-muted-foreground">
              Home page mentions only. Full crawl needed for complete coverage.
            </p>
          ) : null}
          <ul>
            {site.services.clusters.map((c) => {
              const checked = c.topicsPresent.length + c.topicsMissing.length > 0
              return (
                <li
                  key={c.service}
                  className="grid break-inside-avoid grid-cols-[1fr_auto] gap-x-4 border-t border-border py-2 first:border-t-0 print:break-inside-avoid"
                >
                  <div>
                    <p className="text-[14px] font-medium">{c.service}</p>
                    {checked && c.topicsMissing.length ? (
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        <span className="text-[12px] text-muted-foreground">Missing:</span>
                        {c.topicsMissing.slice(0, 4).map((t) => (
                          <Chip key={t} tone="bad">
                            {t}
                          </Chip>
                        ))}
                        {c.topicsMissing.length > 4 ? (
                          <span className="text-[12px] text-muted-foreground">
                            +{c.topicsMissing.length - 4} more
                          </span>
                        ) : null}
                      </div>
                    ) : checked ? (
                      <p className="text-[12px] text-success">Answers every patient question</p>
                    ) : null}
                  </div>
                  <span className="self-start text-[13px] font-medium text-muted-foreground">
                    {site.pagesCrawled <= 1
                      ? 'Mentioned on home page'
                      : `${c.found}/${c.expected} pages`}
                  </span>
                </li>
              )
            })}
          </ul>
        </Section>
      ) : null}

      {site ? (
        <Section title="Local reach" kicker="Where patients search">
          <p className="text-[13px]">
            {site.cities.pagesFound} service-area pages ·{' '}
            {site.cities.hubPage ? 'locations hub present' : 'no locations hub'}
          </p>
          {site.cities.claimedNotBuilt.length ? (
            <>
              <p className="mt-2 text-[12px] text-muted-foreground">
                Cities the site says it serves, with no page of their own
              </p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {site.cities.claimedNotBuilt.map((c) => (
                  <Chip key={c} tone="bad">
                    {c}
                  </Chip>
                ))}
              </div>
              <p className="mt-2 text-[12px] text-muted-foreground">
                Every city above is a search someone nearby is running right now.
              </p>
            </>
          ) : null}
        </Section>
      ) : null}

      <div className="grid grid-cols-2 gap-4 print:grid">
        {site ? (
          <Section title="Proof & trust">
            <CheckList
              items={site.trust.map((t) => ({
                key: t.key,
                label: t.label,
                status: t.status === 'found' ? 'ok' : 'fail',
              }))}
            />
          </Section>
        ) : null}
        {audit.convert ? (
          <Section title="Conversion checks">
            <CheckList items={audit.convert.checks} />
          </Section>
        ) : null}
      </div>

      {gbp?.matched ? (
        <Section title="Google Business Profile">
          <p className="text-[14px] font-medium">{gbp.name}</p>
          <p className="text-[13px] text-muted-foreground">
            {gbp.address} · {gbp.phone}
          </p>
          {gbp.rating != null ? (
            <p className="mt-1 text-[13px]">
              ★ {gbp.rating} ({gbp.reviewCount} Google reviews)
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip tone={gbp.verified ? 'good' : 'bad'}>
              {gbp.verified ? 'Claimed' : 'Not claimed'}
            </Chip>
            <Chip tone={gbp.websiteLinksToGbp ? 'good' : 'bad'}>
              {gbp.websiteLinksToGbp ? 'Site links to profile' : 'Site does not link to profile'}
            </Chip>
            <Chip tone={gbp.reviewLinkOnSite ? 'good' : 'bad'}>
              {gbp.reviewLinkOnSite ? 'Review link on site' : 'No review link on site'}
            </Chip>
          </div>
        </Section>
      ) : null}

      {speed ? (
        <Section title="PageSpeed (mobile)">
          <div className="flex gap-6">
            <Meter label="Performance" value={speed.mobilePerformance} />
            <Meter label="SEO" value={speed.seo} />
            <Meter label="Accessibility" value={speed.accessibility} />
          </div>
        </Section>
      ) : null}

      {r?.domainOverview.data ? (
        <Section title="Domain overview">
          <div className="flex gap-3">
            <Tile value={r.domainOverview.data.domainRating ?? '-'} label="Domain rating" />
            <Tile value={r.domainOverview.data.organicTraffic ?? '-'} label="Monthly traffic" />
            <Tile value={r.domainOverview.data.organicKeywords ?? '-'} label="Keywords" />
            <Tile value={r.domainOverview.data.backlinks ?? '-'} label="Backlinks" />
          </div>
        </Section>
      ) : null}
      {r?.localCompetitors.data ? (
        <Section title="Local competitors">
          <CompetitorList data={r.localCompetitors.data} />
        </Section>
      ) : null}
      {r?.aiVisibility.data ? (
        <Section title="AI visibility">
          <CheckList
            items={r.aiVisibility.data.engines.map((e) => ({
              key: e.engine,
              label: e.engine,
              status: e.cited ? 'ok' : 'fail',
              note: e.cited ? 'cited' : 'not cited',
            }))}
          />
        </Section>
      ) : null}

      {fixes.length ? (
        <section
          className={cn(
            'break-inside-avoid rounded-xl border border-primary/20 bg-primary/5 p-5 print:break-inside-avoid',
            EXACT,
          )}
        >
          <h2 className="border-b-2 border-primary pb-2 text-[13px] font-semibold uppercase tracking-wider text-primary">
            How we fix it
          </h2>
          <ol className="mt-3 flex flex-col gap-3">
            {fixes.map((k, n) => (
              <li key={k} className="flex break-inside-avoid gap-3 print:break-inside-avoid">
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-[13px] font-bold text-primary-foreground',
                    EXACT,
                  )}
                >
                  {n + 1}
                </span>
                <p className="text-[14px] leading-snug">
                  <span className="font-semibold">{FIX[k][0]}</span> {FIX[k][1]}
                </p>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {o ? (
        <section
          className={cn(
            'break-inside-avoid rounded-xl border border-primary/15 bg-primary/5 px-5 py-4 text-[13px] leading-relaxed print:break-inside-avoid',
            EXACT,
          )}
        >
          <span className="font-semibold text-primary">Why this matters: </span>
          when someone searches for a treatment, they call the clinic that shows up first and looks
          trustworthy. Every gap in this report is a share of those calls going to a competitor.
          Closing them is how more of those calls reach this clinic.
        </section>
      ) : null}

      <footer className="break-inside-avoid border-t-2 border-primary pt-3 text-[12px] text-muted-foreground print:break-inside-avoid">
        <p className="font-semibold text-foreground">Wellness Clinic Marketing</p>
        <p>
          Prepared by {report.preparedBy} for {report.preparedFor} ·{' '}
          {formatDateTime(report.generatedAt)}
        </p>
        {/* TODO: WCM contact details */}
      </footer>
    </div>
  )
}

export function ReportPage() {
  const auditId = new URLSearchParams(window.location.search).get('audit')
  const { user, isLoading } = useAuth()
  const report = useReport(user ? auditId : null)

  return (
    <div className="report-root mx-auto max-w-[820px] px-4 py-6 print:max-w-none print:px-[14mm] print:py-[12mm]">
      <div className="mb-4 flex gap-2 print:hidden">
        <Button onClick={() => window.print()}>Save as PDF</Button>
        <Button
          variant="outline"
          onClick={() =>
            navigator.clipboard
              .writeText(auditId ?? '')
              .then(() => toast('Copied'))
              .catch(() => toast('Couldn’t copy'))
          }
        >
          Copy link to audit
        </Button>
        <Button variant="ghost" onClick={() => window.close()}>
          Close
        </Button>
      </div>
      {!auditId ? (
        <p>No audit selected.</p>
      ) : isLoading ? (
        <p>Loading…</p>
      ) : !user ? (
        <p>Sign in from the side panel, then reload.</p>
      ) : report.isPending ? (
        <p>Loading report…</p>
      ) : report.isError || !report.data ? (
        <p>Couldn’t load the report.</p>
      ) : (
        <Body report={report.data} />
      )}
    </div>
  )
}
