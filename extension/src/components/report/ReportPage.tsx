import { CheckIcon, MinusIcon, XIcon } from 'lucide-react'
import { type ReactNode, useEffect } from 'react'
import { CompetitorList } from '@/components/research/ResearchSubTabs'
import { gradeClass } from '@/components/research/shared'
import { Progress } from '@/components/ui/progress'
import { useReport } from '@/hooks/research-queries'
import { useAuth } from '@/hooks/use-auth'
import { REPORT_PRINT_TYPE } from '@/lib/active-tab'
import {
  type BusinessSection,
  type CategoryKey,
  type CheckStatus,
  isLegacyOverview,
  type OverviewCategory,
  type Report,
} from '@/lib/api/research-types'
import { areaProblems } from '@/lib/areas'
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

function barTone(score: number, goodAt = 80, midAt = 60): string {
  if (score >= goodAt) return 'fill-good'
  if (score >= midAt) return 'fill-mid'
  return 'fill-bad'
}

function gradeTone(grade: string): string {
  if (grade === 'A' || grade === 'B') return 'fill-good'
  if (grade === 'C') return 'fill-mid'
  return 'fill-bad'
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="report-section">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function Tile({ value, label, tone }: { value: ReactNode; label: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="report-tile">
      <strong className={cn(tone === 'good' && 'tone-good', tone === 'bad' && 'tone-bad')}>
        {value}
      </strong>
      <span>{label}</span>
    </div>
  )
}

function ScoreLines({ categories }: { categories: OverviewCategory[] }) {
  return (
    <div className="report-scores">
      {categories.map((c) =>
        c.score == null || c.grade == null ? (
          <div key={c.key} className="report-row report-grade-line">
            <span>{c.label}</span>
            <span className="report-muted report-grade-skip">Not assessed</span>
          </div>
        ) : (
          <div key={c.key} className="report-row report-grade-line">
            <span>{c.label}</span>
            <span className="report-grade-meter" aria-hidden="true">
              <span
                className={cn(barTone(c.score, 75, 60), EXACT)}
                style={{ width: `${c.score}%` }}
              />
            </span>
            <span className="report-grade-letter">{c.grade}</span>
          </div>
        ),
      )}
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
        'report-mark',
        status === 'ok' ? 'fill-good' : status === 'warn' ? 'fill-mid' : 'fill-bad',
        EXACT,
      )}
    >
      <Icon className="size-2.5" strokeWidth={3} />
    </span>
  )
}

function GbpCard({ gbp }: { gbp: NonNullable<BusinessSection['gbp']> }) {
  const checks: { key: string; label: string; status: CheckStatus }[] = [
    {
      key: 'claimed',
      label: gbp.verified ? 'Claimed' : 'Not claimed',
      status: gbp.verified ? 'ok' : 'fail',
    },
    {
      key: 'link',
      label: gbp.websiteLinksToGbp ? 'Site links to profile' : 'Site does not link to profile',
      status: gbp.websiteLinksToGbp ? 'ok' : 'fail',
    },
    {
      key: 'reviews',
      label: gbp.reviewLinkOnSite ? 'Review link on site' : 'No review link on site',
      status: gbp.reviewLinkOnSite ? 'ok' : 'fail',
    },
  ]
  const place = [gbp.address, gbp.phone].filter(Boolean).join(' · ')
  return (
    <div className="report-gbp">
      <div className="report-gbp-head">
        <div className="min-w-0">
          {gbp.name ? <p className="report-gbp-name">{gbp.name}</p> : null}
          {gbp.primaryCategory ? <p className="report-gbp-cat">{gbp.primaryCategory}</p> : null}
          {place ? <p>{place}</p> : null}
        </div>
        {gbp.rating != null ? (
          <div className="report-gbp-rating">
            <p className="report-score">
              {gbp.rating} <span aria-hidden="true">★</span>
            </p>
            <p>{gbp.reviewCount ?? 0} Google reviews</p>
          </div>
        ) : null}
      </div>
      <ul className="report-gbp-checks">
        {checks.map((c) => (
          <li key={c.key}>
            <Mark status={c.status} />
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function CheckList({
  items,
}: {
  items: { key: string; label: string; status: CheckStatus; note?: string }[]
}) {
  return (
    <ul className="report-list">
      {items.map((c) => (
        <li key={c.key} className="report-row">
          <Mark status={c.status} />
          <span>
            {c.label}
            {c.note ? <span className="report-muted"> · {c.note}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Meter({ label, value }: { label: string; value: number | null | undefined }) {
  const tone = value == null ? '' : barTone(value, 90, 50)
  return (
    <div className="report-row">
      <div className="report-score-row">
        <span className="report-muted">{label}</span>
        <span className="font-semibold">{value ?? '-'}</span>
      </div>
      <Progress value={value ?? 0} className="report-track" indicatorClassName={cn(tone, EXACT)} />
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
  // Every ranked gap. The offer still covers up to four categories.
  const gaps = o?.topIssues ?? []
  const fixes = o
    ? [...new Set(o.topIssues.map((i) => i.category))].filter((k) => FIX[k]).slice(0, 4)
    : []
  const when = formatDateTime(report.generatedAt)
  const appendix = Boolean(
    r?.domainOverview.data || r?.localCompetitors.data || r?.aiVisibility.data,
  )

  return (
    <>
      <table className="report-pages">
        <thead>
          <tr>
            <td>
              <div className="report-page-gap" />
            </td>
          </tr>
        </thead>
        <tfoot>
          <tr>
            <td>
              <div className="report-page-gap report-page-gap-end" />
            </td>
          </tr>
        </tfoot>
        <tbody>
          <tr className="report-banner">
            <td>
              <Masthead report={report} when={when} />
            </td>
          </tr>
          <tr>
            <td>
              <div className="report-sheet">
                {o ? (
                  <div className="report-cover">
                    <div className="report-stack">
                      <div className="report-grade">
                        <div
                          className={cn(
                            'report-grade-mark',
                            gradeTone(o.grade ?? 'F'),
                            EXACT,
                            gradeClass(o.grade ?? 'F'),
                          )}
                        >
                          {o.grade}
                        </div>
                        <div>
                          <p className="report-score">Overall score: {o.score} / 100</p>
                          {o.provisional ? (
                            <p className="report-muted">
                              {!legacy && reasons.length
                                ? `Provisional: ${reasons.join('; ')}.`
                                : 'Provisional: Google Business Profile not matched; GBP and reviews not scored.'}
                            </p>
                          ) : null}
                          <p className="report-intro">{report.intro}</p>
                        </div>
                      </div>
                      <Section title="Where the score comes from">
                        <ScoreLines
                          categories={o.categories.filter(
                            (c) => !legacy || c.key !== 'getting_the_call',
                          )}
                        />
                        <p className="report-footnote">
                          {legacy
                            ? 'Home page checks only. Google Business Profile and reviews are not scored yet.'
                            : 'Weighted across nine categories. Categories without data are left out of the score.'}
                        </p>
                      </Section>
                      {gaps.length ? (
                        <section className="report-section">
                          <h2>What’s costing them calls</h2>
                          <ol className="report-issues">
                            {gaps.map((i) => (
                              <li key={i.title} className="report-row">
                                <p className="font-semibold">{i.title}</p>
                                <p className="report-muted">{i.detail}</p>
                              </li>
                            ))}
                          </ol>
                        </section>
                      ) : null}
                      <p className="report-bridge">
                        The rest of this report shows where those gaps come from and how they get
                        closed.
                      </p>
                    </div>
                  </div>
                ) : null}

                {o ? (
                  <div className="report-offer">
                    <div className="report-stack">
                      {fixes.length ? (
                        <section className="report-callout">
                          <h2>How we fix it</h2>
                          <ol className="report-fixes">
                            {fixes.map((k) => (
                              <li key={k} className="report-row">
                                <span className="font-semibold">{FIX[k][0]}</span> {FIX[k][1]}
                              </li>
                            ))}
                          </ol>
                        </section>
                      ) : null}
                      <p className="report-why">
                        <span className="font-semibold">Why this matters: </span>
                        when someone searches for a treatment, they call the clinic that shows up
                        first and looks trustworthy. Every gap in this report is a share of those
                        calls going to a competitor. Closing them is how more of those calls reach
                        this clinic.
                      </p>
                    </div>
                  </div>
                ) : null}

                <div className="report-evidence">
                  <div className="report-stack">
                    {site ? (
                      <Section title="Treatment pages">
                        {site.pagesCrawled <= 1 ? (
                          <p className="report-footnote">
                            Home page mentions only. Full crawl needed for complete coverage.
                          </p>
                        ) : null}
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Treatment</th>
                              <th>Coverage</th>
                              <th>What’s missing</th>
                            </tr>
                          </thead>
                          <tbody>
                            {site.services.clusters.map((c) => {
                              const checked = c.topicsPresent.length + c.topicsMissing.length > 0
                              const missing = c.topicsMissing.slice(0, 4).join(', ')
                              const extra =
                                c.topicsMissing.length > 4 ? c.topicsMissing.length - 4 : 0
                              return (
                                <tr key={c.service}>
                                  <td className="font-medium">{c.service}</td>
                                  <td>
                                    {site.pagesCrawled <= 1
                                      ? 'Mentioned on home page'
                                      : `${c.found}/${c.expected} pages`}
                                  </td>
                                  <td>
                                    {checked && c.topicsMissing.length
                                      ? `${missing}${extra ? ` +${extra} more` : ''}`
                                      : checked
                                        ? 'Answers every patient question'
                                        : 'Not reviewed'}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </Section>
                    ) : null}

                    {site ? (
                      <Section title="Local reach">
                        <p>
                          {site.cities.pagesFound} service-area pages ·{' '}
                          {site.cities.hubPage ? 'locations hub present' : 'no locations hub'}
                        </p>
                        {site.cities.areas?.some((a) => a.status === 'needs_work') ? (
                          <p className="report-muted">
                            City pages that need work:{' '}
                            {site.cities.areas
                              .filter((a) => a.status === 'needs_work')
                              .map((a) => `${a.name} (${areaProblems(a).join(', ')})`)
                              .join('; ')}
                            .
                          </p>
                        ) : null}
                        {site.cities.claimedNotBuilt.length ? (
                          <>
                            <p className="report-muted">
                              Cities the site says it serves, with no page of their own:{' '}
                              {site.cities.claimedNotBuilt.join(', ')}.
                            </p>
                            <p className="report-footnote">
                              Every city above is a search someone nearby is running right now.
                            </p>
                          </>
                        ) : null}
                      </Section>
                    ) : null}

                    {site || audit.convert ? (
                      <div className={site && audit.convert ? 'report-split' : undefined}>
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
                    ) : null}

                    {gbp?.matched ? (
                      <Section title="Google Business Profile">
                        <GbpCard gbp={gbp} />
                      </Section>
                    ) : null}

                    {audit.onPage?.summary ? (
                      <Section title="On-page SEO">
                        <div className="report-tiles">
                          <Tile value={audit.onPage.summary.score} label="On-page score" />
                          <Tile
                            value={audit.onPage.summary.critical + audit.onPage.summary.high}
                            label="Serious problems"
                            tone={
                              audit.onPage.summary.critical + audit.onPage.summary.high
                                ? 'bad'
                                : 'good'
                            }
                          />
                          <Tile value={audit.onPage.pages?.length ?? 1} label="Pages checked" />
                        </div>
                        {audit.onPage.summary.topFixes.length ? (
                          <ol className="report-fixes">
                            {audit.onPage.summary.topFixes.slice(0, 5).map((f) => (
                              <li key={f.key} className="report-row">
                                <span className="font-semibold">{f.title}.</span> {f.detail}
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="report-muted">No important on-page problems were found.</p>
                        )}
                        <p className="report-note">
                          <span className="font-semibold">Why this matters: </span>
                          Google reads the title, the heading and the text on each page. When those
                          are missing or repeated, people searching for a treatment are less likely
                          to find this clinic.
                        </p>
                      </Section>
                    ) : null}

                    {speed ? (
                      <Section title="PageSpeed">
                        <div className="report-speed">
                          <p className="report-speed-label">Mobile</p>
                          <div className="report-meters">
                            <Meter label="Performance" value={speed.mobilePerformance} />
                            <Meter label="SEO" value={speed.seo} />
                            <Meter label="Accessibility" value={speed.accessibility} />
                          </div>
                        </div>
                        {speed.desktop ? (
                          <div className="report-speed">
                            <p className="report-speed-label">Desktop</p>
                            <div className="report-meters">
                              <Meter label="Performance" value={speed.desktop.performance} />
                              <Meter label="SEO" value={speed.desktop.seo} />
                              <Meter label="Accessibility" value={speed.desktop.accessibility} />
                            </div>
                          </div>
                        ) : null}
                      </Section>
                    ) : null}

                    {appendix ? (
                      <div className="report-appendix report-stack">
                        {r?.domainOverview.data ? (
                          <Section title="Domain overview">
                            <div className="report-tiles">
                              <Tile
                                value={r.domainOverview.data.domainRating ?? '-'}
                                label="Domain rating"
                              />
                              <Tile
                                value={r.domainOverview.data.organicTraffic ?? '-'}
                                label="Monthly traffic"
                              />
                              <Tile
                                value={r.domainOverview.data.organicKeywords ?? '-'}
                                label="Keywords"
                              />
                              <Tile
                                value={r.domainOverview.data.backlinks ?? '-'}
                                label="Backlinks"
                              />
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
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <footer className="report-running">
        <span>Wellness Clinic Marketing</span>
        <span>{audit.domain}</span>
      </footer>
    </>
  )
}

function Masthead({ report, when }: { report: Report; when: string }) {
  return (
    <header className={cn('report-masthead', EXACT)}>
      <div className="report-masthead-inner">
        <div className="min-w-0 flex-1">
          <h1>Website &amp; Local Visibility Report</h1>
          <div className="report-meta">
            <p className="font-medium">{report.audit.domain}</p>
            <p>Prepared for {report.preparedFor}</p>
            <p>{when}</p>
          </div>
        </div>
        <span className="report-logo-lockup">
          <img src="/brand/logo-head-light.webp" alt="WCM" className="report-logo" />
        </span>
      </div>
    </header>
  )
}

export function ReportPage() {
  const auditId = new URLSearchParams(window.location.search).get('audit')
  const { user, isLoading } = useAuth()
  const report = useReport(user ? auditId : null)

  useEffect(() => {
    const onMessage = (message: unknown, _sender: unknown, sendResponse: (r: unknown) => void) => {
      if (!message || typeof message !== 'object') return
      const data = message as { type?: string; auditId?: string }
      if (data.type !== REPORT_PRINT_TYPE || !data.auditId || data.auditId !== auditId) return
      console.info('[report] pdf start', { auditId })
      const root = document.querySelector('.report-pages')
      if (!(root instanceof HTMLElement)) {
        console.error('[report] pdf failed', { auditId, reason: 'report not ready' })
        sendResponse({ ok: false })
        return true
      }
      void import('@/lib/report-pdf')
        .then(({ downloadReportPdf }) => downloadReportPdf(root))
        .then(() => sendResponse({ ok: true }))
        .catch((err: unknown) => {
          console.error('[report] pdf failed', { auditId, err })
          sendResponse({ ok: false })
        })
      return true
    }
    browser.runtime.onMessage.addListener(onMessage)
    return () => browser.runtime.onMessage.removeListener(onMessage)
  }, [auditId])

  return (
    <div className="report-root">
      {!auditId ? (
        <p className="report-frame">No audit selected.</p>
      ) : isLoading ? (
        <p className="report-frame">Loading…</p>
      ) : !user ? (
        <p className="report-frame">Sign in from the side panel, then reload.</p>
      ) : report.isPending ? (
        <p className="report-frame">Loading report…</p>
      ) : report.isError || !report.data ? (
        <p className="report-frame">Couldn’t load the report.</p>
      ) : (
        <Body report={report.data} />
      )}
    </div>
  )
}
