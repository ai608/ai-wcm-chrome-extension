import { CameraIcon, WandSparklesIcon } from 'lucide-react'
import { Block, Chip, ChipRow, ExtLink, Row } from '@/components/research/shared'
import { Button } from '@/components/ui/button'
import type { Audit } from '@/lib/api/research-types'

// ponytail: UI only. No screenshot capture or concept generation exists yet; wire onClick when it does.
function ActionRows() {
  const label = 'text-[12px] font-semibold uppercase leading-tight text-foreground/70'
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className={label}>Mobile experience</span>
        <Button variant="outline" size="xs" disabled title="Coming soon">
          <CameraIcon /> Capture screenshots
        </Button>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={label}>Redesign concept</span>
        <Button variant="outline" size="xs" disabled title="Coming soon">
          <WandSparklesIcon /> Build concept
        </Button>
      </div>
    </div>
  )
}

/** Website facts shared by Call Mode research and Research Mode Business. */
export function WebsiteSummary({
  audit,
  showActions = false,
}: {
  audit: Audit
  showActions?: boolean
}) {
  const { business, site } = audit
  const services =
    site?.services.clusters.filter((c) => c.found > 0).map((c) => c.service.split(' (')[0]) ?? []
  const description = audit.onPage?.essentials.find((e) => e.key === 'meta_description')?.value
  const gbpWebsiteMatch = business?.gbp?.matched && business.gbp.websiteLinksToGbp

  return (
    <Block title="Website">
      <Row label="URL">
        <ExtLink href={audit.url}>{audit.domain}</ExtLink>{' '}
        {gbpWebsiteMatch ? <Chip tone="good">VERIFIED</Chip> : null}
      </Row>
      {site ? (
        <Row label="Platform">
          {[site.platform.name, site.platform.detail].filter(Boolean).join(' · ')}
        </Row>
      ) : null}
      {audit.onPage ? (
        <Row label="Page title">
          {audit.onPage.essentials.find((e) => e.key === 'title')?.value ?? '-'}
        </Row>
      ) : null}
      {description ? <Row label="Description">{description}</Row> : null}
      {services.length ? <ChipRow label="Services" items={services} /> : null}
      {site?.cities.cityPages.length ? (
        <ChipRow label="Areas served (website)" items={site.cities.cityPages} />
      ) : null}
      {showActions ? (
        <div className="mt-2">
          <ActionRows />
        </div>
      ) : null}
    </Block>
  )
}
