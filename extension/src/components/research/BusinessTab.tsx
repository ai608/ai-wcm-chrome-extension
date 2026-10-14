import { Globe } from 'lucide-react'
import { Block, Chip, ExtLink, Row } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import type { BusinessSection } from '@/lib/api/research-types'

const NETWORK: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  linkedin: 'LinkedIn',
  x: 'X',
}

export function GbpCard({ gbp }: { gbp: BusinessSection['gbp'] }) {
  if (!gbp?.matched) {
    return (
      <Alert>
        <AlertDescription>
          No Google Business Profile matched for this website.
          {gbp?.matchReason ? ` ${gbp.matchReason}.` : ''}
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <Block title="Google Business Profile">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-semibold">{gbp.name}</span>
        {gbp.verified ? <Badge variant="secondary">VERIFIED</Badge> : null}
      </div>
      {gbp.primaryCategory ? (
        <div className="mt-1">
          <Chip>{gbp.primaryCategory}</Chip>
        </div>
      ) : null}
      <div className="mt-2 flex flex-col gap-0.5 text-[13px] text-muted-foreground">
        {gbp.address ? <p>{gbp.address}</p> : null}
        {gbp.phone ? <p>{gbp.phone}</p> : null}
        {gbp.rating != null ? (
          <p>
            ★ {gbp.rating} ({gbp.reviewCount ?? 0} Google reviews)
          </p>
        ) : null}
        {gbp.lat != null && gbp.lng != null && gbp.mapsUrl ? (
          <p>
            <ExtLink href={gbp.mapsUrl}>
              {gbp.lat.toFixed(4)}, {gbp.lng.toFixed(4)}
            </ExtLink>
          </p>
        ) : null}
      </div>
      {gbp.mapsUrl ? (
        <p className="mt-2 text-[13px]">
          <ExtLink href={gbp.mapsUrl}>Open Google Business Profile</ExtLink>
        </p>
      ) : null}
    </Block>
  )
}

export function CompanyCard({ company }: { company: BusinessSection['company'] }) {
  if (!company) return null
  const tech = company.technologies.slice(0, 12)
  const more = company.technologies.length - tech.length
  return (
    <Block title="Company (Apollo)">
      <div className="flex flex-wrap gap-1.5">
        {company.industry ? <Chip>{company.industry}</Chip> : null}
        {company.employeeCount != null ? <Chip>{company.employeeCount} employees</Chip> : null}
        {company.foundedYear ? <Chip>Founded {company.foundedYear}</Chip> : null}
      </div>
      {company.linkedinUrl ? (
        <p className="mt-2 text-[13px]">
          <ExtLink href={company.linkedinUrl}>LinkedIn</ExtLink>
        </p>
      ) : null}
      {tech.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tech.map((t) => (
            <Chip key={t}>{t}</Chip>
          ))}
          {more > 0 ? <Chip>+{more} more</Chip> : null}
        </div>
      ) : null}
    </Block>
  )
}

export function BusinessTab({ business }: { business: BusinessSection }) {
  return (
    <div className="flex flex-col gap-3">
      <GbpCard gbp={business.gbp} />
      {business.gbp?.matched ? (
        <Block>
          <Row label="Website links to GBP" status={business.gbp.websiteLinksToGbp ? 'ok' : 'fail'}>
            {business.gbp.websiteLinksToGbp ? 'Yes' : 'No'}
          </Row>
          <Row label="Review link on site" status={business.gbp.reviewLinkOnSite ? 'ok' : 'fail'}>
            {business.gbp.reviewLinkOnSite ? 'Yes' : 'No'}
          </Row>
          <Row
            label="NAP consistent"
            status={
              business.nap.consistentWithGbp == null
                ? 'info'
                : business.nap.consistentWithGbp
                  ? 'ok'
                  : 'fail'
            }
          >
            {business.nap.consistentWithGbp == null
              ? 'Unknown'
              : business.nap.consistentWithGbp
                ? 'Matches GBP'
                : 'Differs from GBP'}
          </Row>
        </Block>
      ) : null}
      <CompanyCard company={business.company} />
      {business.socials.length ? (
        <Block title="Socials">
          <ul className="flex flex-col gap-1.5 text-[13px]">
            {business.socials.map((s) => {
              return (
                <li key={s.url} className="flex items-center gap-2">
                  <Globe className="size-4 text-muted-foreground" />
                  <ExtLink href={s.url}>{NETWORK[s.network] ?? s.network}</ExtLink>
                </li>
              )
            })}
          </ul>
        </Block>
      ) : null}
    </div>
  )
}
