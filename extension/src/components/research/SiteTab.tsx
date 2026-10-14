import { Block, Chip, ExtLink, Row, StatBox, SubTabs } from '@/components/research/shared'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import type { Audit, SiteSection } from '@/lib/api/research-types'
import { downloadCsv, toCsv } from '@/lib/csv'
import { relativeTime } from '@/lib/time'
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
    for (const c of site.cities.claimedNotBuilt)
      gaps.push({ area: 'Cities', item: `${c} (claimed, no page)` })
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
            No city pages means no map-radius coverage beyond the home market — usually the biggest
            local SEO gap.
          </p>
        ) : null}
        <Row label="Hub page" status={c.hubPage ? 'ok' : 'warn'}>
          {c.hubPage ? '/locations/ or /service-areas/ detected' : 'Not detected'}
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
      {c.claimedNotBuilt.length ? (
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
  return (
    <div className="flex flex-col gap-3">
      <Block>
        <Row label="Blog URL">{b.url ? <ExtLink href={b.url}>{b.url}</ExtLink> : 'None found'}</Row>
        <Row label="Posts">{b.postCount}</Row>
        <Row label="Last post" status={b.postsLast6Months ? 'ok' : 'warn'}>
          {b.lastPostAt
            ? `${new Date(b.lastPostAt).toLocaleDateString()} (${relativeTime(b.lastPostAt)})`
            : '—'}
        </Row>
        <Row label="Frequency">
          {b.postsLast6Months} in last 6 months, {b.postsLast12Months} in last 12
        </Row>
        <Row label="Links to services" status={b.linksToServices ? 'ok' : 'fail'}>
          {b.linksToServices ? 'Yes' : 'No'}
        </Row>
      </Block>
      <Button
        variant="outline"
        size="sm"
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
                <ExtLink href={x.url}>Found</ExtLink>
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
        onClick={() => downloadCsv(audit.domain, 'gap-inventory', toCsv(gapInventory(audit)))}
      >
        Export full gap inventory to CSV
      </Button>
    </div>
  )
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
      <SubTabs value={sub} onChange={(v) => setSub('site', v)} items={SUBS} />
      {sub === 'services' ? <Services s={site.services} /> : null}
      {sub === 'cities' ? <Cities c={site.cities} /> : null}
      {sub === 'proof' ? <Proof p={site.proof} /> : null}
      {sub === 'blog' ? <Blog audit={audit} b={site.blog} /> : null}
      {sub === 'trust' ? <Trust audit={audit} t={site.trust} /> : null}
    </div>
  )
}
