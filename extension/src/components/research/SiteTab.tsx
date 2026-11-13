import { Block, Chip, ExtLink, Row, StatBox, SubTabs } from '@/components/research/shared'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import type { Audit, SiteSection } from '@/lib/api/research-types'
import { areaProblems } from '@/lib/areas'
import { downloadCsv, toCsv } from '@/lib/csv'
import { formatPostDate, relativeTime } from '@/lib/time'
import { usePanelStore } from '@/stores/panel-store'

type Sub = 'services' | 'cities' | 'proof' | 'blog' | 'trust'
const SUBS: { value: Sub; label: string }[] = [
  { value: 'services', label: 'Services' },
  { value: 'cities', label: 'Cities' },
  { value: 'proof', label: 'Proof' },
  { value: 'blog', label: 'Blog' },
  { value: 'trust', label: 'Trust' },
]

type Gap = { area: string; item: string }

export function gapInventory(audit: Audit): Gap[] {
  const gaps: Gap[] = []
  const site = audit.site
  if (site) {
    for (const c of site.services.clusters) {
      for (const t of c.topicsMissing) gaps.push({ area: `Services: ${c.service}`, item: t })
    }
    if (site.cities.pagesFound === 0) gaps.push({ area: 'Cities', item: 'No service-area pages' })
    if (!site.cities.hubPage) gaps.push({ area: 'Cities', item: 'No hub page' })
    if (site.cities.areas?.length) {
      for (const a of site.cities.areas) {
        if (a.status === 'missing')
          gaps.push({ area: 'Cities', item: `${a.name} (claimed, no page)` })
        if (a.status === 'mentioned')
          gaps.push({ area: 'Cities', item: `${a.name} (mentioned, no page of its own)` })
        if (a.status === 'needs_work')
          gaps.push({ area: 'Cities', item: `${a.name} page: ${areaProblems(a).join(', ')}` })
      }
    } else {
      for (const c of site.cities.claimedNotBuilt)
        gaps.push({ area: 'Cities', item: `${c} (claimed, no page)` })
    }
    for (const p of site.unfinishedPages ?? [])
      gaps.push({ area: 'Clean-up', item: `${pathOf(p.url)}: ${p.reason}` })
    if (!site.proof.beforeAfterGallery) gaps.push({ area: 'Proof', item: 'Before/after gallery' })
    if (!site.proof.testimonialPages) gaps.push({ area: 'Proof', item: 'Testimonial pages' })
    if (!site.proof.reviewsPage) gaps.push({ area: 'Proof', item: 'Reviews page' })
    if (!site.proof.caseStudyPages) gaps.push({ area: 'Proof', item: 'Case studies' })
    for (const t of site.trust)
      if (t.status === 'missing') gaps.push({ area: 'Trust', item: t.label })
  }
  if (audit.schema && !audit.schema.hasLocalBusiness)
    gaps.push({ area: 'Schema', item: 'LocalBusiness' })
  if (audit.schema && !audit.schema.hasFaqPage) gaps.push({ area: 'Schema', item: 'FAQPage' })
  for (const c of audit.convert?.checks ?? []) {
    if (c.status === 'fail' || c.status === 'warn') gaps.push({ area: 'Convert', item: c.label })
  }
  return gaps
}

function Services({ s }: { s: SiteSection['services'] }) {
  const low = s.clusterPagesFound < s.clusterPagesExpected / 2
  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <StatBox
          label="cluster pages"
          value={`${s.clusterPagesFound}/${s.clusterPagesExpected}`}
          tone={low ? 'bad' : 'good'}
        />
      </div>
      {s.typesBy === 'rules' ? (
        <p className="text-[12px] text-muted-foreground">
          Page types by address and menu only: the AI check did not run, so a blog post can be
          counted as a service page.
        </p>
      ) : null}
      <Accordion className="rounded-md border border-border px-2.5">
        {s.clusters.map((c) => (
          <AccordionItem key={c.service} value={c.service}>
            <AccordionTrigger className="py-2 text-[13px] font-medium">
              <span className="flex-1">{c.service}</span>
              <span className={c.found < c.expected / 2 ? 'text-destructive' : 'text-success'}>
                {c.found}/{c.expected}
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="flex flex-wrap gap-1.5">
                {c.topicsPresent.map((t) => (
                  <Chip key={t} tone="good">
                    ✓ {t}
                  </Chip>
                ))}
                {c.topicsMissing.map((t) => (
                  <Chip key={t} tone="bad">
                    ✗ {t}
                  </Chip>
                ))}
              </div>
              {c.pages.length ? (
                <ul className="mt-2 flex flex-col gap-0.5 text-[12px]">
                  {c.pages.map((p) => (
                    <li key={p} className="break-all">
                      <ExtLink href={p}>{p}</ExtLink>
                    </li>
                  ))}
                </ul>
              ) : null}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
      <p className="text-[12px] text-muted-foreground">
        Each missing topic is a page the content team can quote and build.
      </p>
    </div>
  )
}

function Cities({ c }: { c: SiteSection['cities'] }) {
  return (
    <div className="flex flex-col gap-3">
      <Block>
        <Row label="Pages found" status={c.pagesFound ? 'ok' : 'fail'}>
          {c.pagesFound} service-area / city pages
        </Row>
        {c.pagesFound === 0 ? (
          <p className="text-[12px] text-muted-foreground">
            No city pages means no map-radius coverage beyond the home market, usually the biggest
            local SEO gap.
          </p>
        ) : null}
        <Row label="Hub page" status={c.hubPage ? 'ok' : 'warn'}>
          {c.hubPage ? 'A page that gathers the areas was found' : 'Not detected'}
        </Row>
      </Block>
      {c.cityPages.length ? (
        <div className="flex flex-wrap gap-1.5">
          {c.cityPages.map((p) => (
            <Chip key={p} tone="good">
              {p}
            </Chip>
          ))}
        </div>
      ) : null}
      {c.areas?.length ? (
        <Block title="Areas the site says it serves">
          {c.areas.map((a) => (
            <Row
              key={a.name}
              label={a.kind === 'location' ? `${a.name} (office)` : a.name}
              status={a.status === 'covered' ? 'ok' : a.status === 'missing' ? 'fail' : 'warn'}
            >
              {a.status === 'covered'
                ? 'Has its own page'
                : a.status === 'needs_work'
                  ? `Page needs work: ${areaProblems(a).join(', ')}`
                  : a.status === 'mentioned'
                    ? 'Named in the text, no page of its own'
                    : 'No page, not mentioned elsewhere'}
            </Row>
          ))}
        </Block>
      ) : c.claimedNotBuilt.length ? (
        <Block title="Claimed but no page">
          <div className="flex flex-wrap gap-1.5">
            {c.claimedNotBuilt.map((p) => (
              <Chip key={p} tone="bad">
                {p}
              </Chip>
            ))}
          </div>
        </Block>
      ) : null}
    </div>
  )
}

function Proof({ p }: { p: SiteSection['proof'] }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <StatBox
          label="Before/after"
          value={p.beforeAfterGallery ? '✓' : '✗'}
          tone={p.beforeAfterGallery ? 'good' : 'bad'}
        />
        <StatBox
          label="Testimonial pages"
          value={p.testimonialPages}
          tone={p.testimonialPages ? 'good' : 'bad'}
        />
        <StatBox
          label="Reviews page"
          value={p.reviewsPage ? '✓' : '✗'}
          tone={p.reviewsPage ? 'good' : 'bad'}
        />
      </div>
      <Block>
        <Row label="Case studies" status={p.caseStudyPages ? 'ok' : 'warn'}>
          {p.caseStudyPages}
        </Row>
        <Row label="Video testimonials" status={p.videoTestimonials ? 'ok' : 'warn'}>
          {p.videoTestimonials ? 'Yes' : 'None found'}
        </Row>
      </Block>
    </div>
  )
}

function Blog({ audit, b }: { audit: Audit; b: SiteSection['blog'] }) {
  // Counts come from posts whose date we found. When many posts have none, they are minimums.
  const partial = b.datedPosts != null && b.postCount > 0 && b.datedPosts < b.postCount
  const dateKnown = b.lastPostAt != null
  return (
    <div className="flex flex-col gap-3">
      <Block>
        <Row label="Blog URL">{b.url ? <ExtLink href={b.url}>{b.url}</ExtLink> : 'None found'}</Row>
        <Row label="Posts">{b.postCount}</Row>
        <Row
          label="Last post"
          status={!dateKnown ? 'info' : b.postsLast6Months ? 'ok' : partial ? 'info' : 'warn'}
        >
          {b.lastPostAt
            ? `${formatPostDate(b.lastPostAt)} (${relativeTime(b.lastPostAt)})`
            : 'Date not found'}
        </Row>
        <Row label="Frequency">
          {partial ? 'At least ' : ''}
          {b.postsLast6Months} in the last 6 months, {b.postsLast12Months} in the last 12 months
          {partial ? (
            <span className="mt-0.5 block text-[12px]">
              Dates found for {b.datedPosts} of {b.postCount} posts.
            </span>
          ) : null}
        </Row>
        <Row label="Links to services" status={b.linksToServices ? 'ok' : 'fail'}>
          {b.linksToServices ? 'Yes' : 'No'}
        </Row>
      </Block>
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() =>
          downloadCsv(
            audit.domain,
            'blog-posts',
            toCsv(b.posts.map((p) => ({ url: p.url, title: p.title, published: p.publishedAt }))),
          )
        }
      >
        Export posts to CSV
      </Button>
    </div>
  )
}

function Trust({ audit, t }: { audit: Audit; t: SiteSection['trust'] }) {
  return (
    <div className="flex flex-col gap-3">
      <Block>
        {t.map((x) => (
          <Row key={x.key} label={x.label} status={x.status === 'found' ? 'ok' : 'warn'}>
            {x.status === 'found' ? (
              x.url ? (
                <ExtLink href={x.url}>{x.section ? 'Section on a page' : 'Found'}</ExtLink>
              ) : (
                'Found'
              )
            ) : (
              'Missing'
            )}
          </Row>
        ))}
      </Block>
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => downloadCsv(audit.domain, 'gap-inventory', toCsv(gapInventory(audit)))}
      >
        Export full gap inventory to CSV
      </Button>
    </div>
  )
}

/** Pages that should not be live, or carry builder default text: a concrete fix for the clinic. */
function CleanUp({ pages }: { pages: NonNullable<SiteSection['unfinishedPages']> }) {
  if (!pages.length) return null
  return (
    <Block title={`Pages to clean up (${pages.length})`}>
      {pages.map((p) => (
        <Row key={p.url} label={pathOf(p.url)} status={p.counted ? 'warn' : 'fail'}>
          <ExtLink href={p.url}>{p.reason}</ExtLink>
        </Row>
      ))}
    </Block>
  )
}

function pathOf(url: string): string {
  try {
    return new URL(url).pathname || '/'
  } catch {
    return url
  }
}

export function SiteTab({ audit, site }: { audit: Audit; site: SiteSection }) {
  const sub = (usePanelStore((s) => s.researchSubTab.site) as Sub | undefined) ?? 'services'
  const setSub = usePanelStore((s) => s.setResearchSubTab)
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13px] text-muted-foreground">
        {site.platform.name}
        {site.platform.detail ? ` (${site.platform.detail})` : ''} · {site.pagesCrawled} pages
        crawled
      </p>
      <CleanUp pages={site.unfinishedPages ?? []} />
      <SubTabs value={sub} onChange={(v) => setSub('site', v)} items={SUBS} />
      {sub === 'services' ? <Services s={site.services} /> : null}
      {sub === 'cities' ? <Cities c={site.cities} /> : null}
      {sub === 'proof' ? <Proof p={site.proof} /> : null}
      {sub === 'blog' ? <Blog audit={audit} b={site.blog} /> : null}
      {sub === 'trust' ? <Trust audit={audit} t={site.trust} /> : null}
    </div>
  )
}
