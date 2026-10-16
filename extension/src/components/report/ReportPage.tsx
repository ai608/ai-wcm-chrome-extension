import type { ReactNode } from 'react'
import { CompetitorList } from '@/components/research/ResearchSubTabs'
import { Chip, gradeClass, StatusDot } from '@/components/research/shared'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toast'
import { useReport } from '@/hooks/research-queries'
import { useAuth } from '@/hooks/use-auth'
import type { Report } from '@/lib/api/research-types'
import { formatDateTime } from '@/lib/time'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="break-inside-avoid rounded-lg border border-border p-4">
      <h2 className="mb-2 text-[16px] font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function Body({ report }: { report: Report }) {
  const { audit } = report
  const o = audit.overview
  const gbp = audit.business?.gbp
  const site = audit.site
  const r = audit.research
  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center gap-3 rounded-lg bg-primary px-5 py-4 text-primary-foreground">
        <img src="/brand/logo-head-light.webp" alt="WCM" className="h-8 w-auto" />
        <h1 className="flex-1 text-[18px] font-semibold">Website &amp; Local Visibility Report</h1>
        <div className="text-right text-[13px]">
          <p className="font-medium">{audit.domain}</p>
          <p>{formatDateTime(report.generatedAt)}</p>
        </div>
      </header>

      {o ? (
        <section className="break-inside-avoid rounded-lg border border-border p-4">
          <div className="flex items-center gap-4">
            <div
              className={`flex size-20 shrink-0 items-center justify-center rounded-full text-4xl font-bold ${gradeClass(o.grade)}`}
            >
              {o.grade}
            </div>
            <div>
              <p className="text-[15px] text-muted-foreground">Prepared for {report.preparedFor}</p>
              <p className="text-2xl font-semibold">Overall score: {o.score} / 100</p>
              {o.provisional ? (
                <p className="text-[13px] text-muted-foreground">
                  Provisional: Google Business Profile not matched; GBP and reviews not scored.
                </p>
              ) : null}
            </div>
          </div>
          <p className="mt-3 text-[14px] leading-relaxed">{report.intro}</p>
        </section>
      ) : null}

      {o ? (
        <Section title="Where the score comes from">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {o.categories.map((c) => (
              <div key={c.key}>
                <div className="flex justify-between text-[13px]">
                  <span>{c.label}</span>
                  <span className="font-semibold">{c.grade}</span>
                </div>
                <Progress
                  value={c.score}
                  indicatorClassName={
                    c.score >= 80
                      ? 'bg-success'
                      : c.score >= 60
                        ? 'bg-accent-wcm'
                        : 'bg-destructive'
                  }
                />
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {o ? (
        <Section title="What’s costing them calls">
          <ol className="flex list-decimal flex-col gap-2 pl-5 text-[14px]">
            {o.topIssues.map((i) => (
              <li key={i.title}>
                <p className="font-medium">{i.title}</p>
                <p className="text-muted-foreground">{i.detail}</p>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}

      {gbp?.matched ? (
        <Section title="Google Business Profile">
          <p className="text-[14px] font-medium">{gbp.name}</p>
          <p className="text-[13px] text-muted-foreground">
            {gbp.address} · {gbp.phone}
          </p>
          {gbp.rating != null ? (
            <p className="text-[13px]">
              ★ {gbp.rating} ({gbp.reviewCount} Google reviews)
            </p>
          ) : null}
        </Section>
      ) : null}

      {site ? (
        <Section title="Services coverage">
          <table className="w-full text-[13px]">
            <tbody>
              {site.services.clusters.map((c) => (
                <tr key={c.service} className="border-t border-border">
                  <td className="py-1">{c.service}</td>
                  <td
                    className={`text-right font-medium ${c.found < c.expected / 2 ? 'text-destructive' : 'text-success'}`}
                  >
                    {c.found}/{c.expected}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {site ? (
        <Section title="City pages">
          <p className="text-[13px]">
            {site.cities.pagesFound} service-area pages ·{' '}
            {site.cities.hubPage ? 'hub page present' : 'no hub page'}
          </p>
          {site.cities.claimedNotBuilt.length ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {site.cities.claimedNotBuilt.map((c) => (
                <Chip key={c} tone="bad">
                  {c}
                </Chip>
              ))}
            </div>
          ) : null}
        </Section>
      ) : null}

      {site ? (
        <Section title="Proof & trust">
          <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-[13px]">
            {site.trust.map((t) => (
              <li key={t.key} className="flex gap-2">
                <StatusDot status={t.status === 'found' ? 'ok' : 'warn'} />
                {t.label}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {audit.convert ? (
        <Section title="Conversion checks">
          <ul className="flex flex-col gap-1 text-[13px]">
            {audit.convert.checks.map((c) => (
              <li key={c.key} className="flex gap-2">
                <StatusDot status={c.status} />
                {c.label}
                {c.note ? <span className="text-muted-foreground">· {c.note}</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {audit.onPage?.pagespeed ? (
        <Section title="PageSpeed (mobile)">
          <p className="text-[13px]">
            Performance {audit.onPage.pagespeed.mobilePerformance ?? '-'} · SEO{' '}
            {audit.onPage.pagespeed.seo ?? '-'} · Accessibility{' '}
            {audit.onPage.pagespeed.accessibility ?? '-'}
          </p>
        </Section>
      ) : null}

      {r?.domainOverview.data ? (
        <Section title="Domain overview">
          <p className="text-[13px]">
            DR {r.domainOverview.data.domainRating ?? '-'} · traffic{' '}
            {r.domainOverview.data.organicTraffic ?? '-'} · keywords{' '}
            {r.domainOverview.data.organicKeywords ?? '-'} · backlinks{' '}
            {r.domainOverview.data.backlinks ?? '-'}
          </p>
        </Section>
      ) : null}
      {r?.localCompetitors.data ? (
        <Section title="Local competitors">
          <CompetitorList data={r.localCompetitors.data} />
        </Section>
      ) : null}
      {r?.aiVisibility.data ? (
        <Section title="AI visibility">
          <ul className="flex flex-col gap-1 text-[13px]">
            {r.aiVisibility.data.engines.map((e) => (
              <li key={e.engine}>
                {e.engine}: {e.cited ? '✓ cited' : '✗ not cited'}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <footer className="border-t border-border pt-3 text-[12px] text-muted-foreground">
        Prepared by {report.preparedBy} · {formatDateTime(report.generatedAt)}
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
    <div className="mx-auto max-w-[820px] px-4 py-6">
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
