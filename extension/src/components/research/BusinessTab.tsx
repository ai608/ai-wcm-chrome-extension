import { BadgeCheck, Copy, ExternalLink, Globe, MapPin, Phone, Star } from 'lucide-react'
import type { ReactNode } from 'react'
import { SocialIcon } from '@/components/research/SocialIcon'
import { StaticMap } from '@/components/research/StaticMap'
import { Block, ChipRow, ExtLink, Row } from '@/components/research/shared'
import { WebsiteSummary } from '@/components/research/WebsiteSummary'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toast'
import type { Audit, BusinessSection } from '@/lib/api/research-types'
import { cn } from '@/lib/utils'

const NETWORK: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  linkedin: 'LinkedIn',
  x: 'X',
}

function safeHref(href: string): string | null {
  try {
    const u = new URL(href)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : null
  } catch {
    return null
  }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      title={`Copy ${label}`}
      aria-label={`Copy ${label}`}
      className="shrink-0 text-muted-foreground hover:text-foreground"
      onClick={() =>
        navigator.clipboard
          .writeText(text)
          .then(() => toast('Copied'))
          .catch(() => toast('Couldn’t copy'))
      }
    >
      <Copy aria-hidden="true" />
    </Button>
  )
}

function matchedOn(gbp: NonNullable<BusinessSection['gbp']>): string | null {
  const reasons = gbp.matchReasons?.length ? gbp.matchReasons : null
  if (!reasons) return gbp.matchReason ? `Matched on ${gbp.matchReason}` : null
  const list =
    reasons.length > 1 ? `${reasons.slice(0, -1).join(', ')} and ${reasons.at(-1)}` : reasons[0]
  return `Matched on ${list}`
}

export function GbpCard({
  gbp,
  socials = [],
  website,
  bordered = false,
  business,
}: {
  gbp: BusinessSection['gbp']
  socials?: BusinessSection['socials']
  website?: string | null
  bordered?: boolean
  /** When set, profile signals render under the card as part of GBP. */
  business?: BusinessSection
}) {
  if (!gbp?.matched) {
    const note = business?.gbpNote ? ` ${business.gbpNote}` : ''
    // "Not found" is a finding about the clinic; "not checked" says nothing about it.
    const text =
      business?.gbpStatus === 'not_found'
        ? `No Google Business Profile matched this website.${note}`
        : business?.gbpStatus === 'not_checked'
          ? `Google Business Profile was not checked, so there is no finding about it.${note}`
          : `Google Business Profile data is not available for this audit.${
              gbp?.matchReason ? ` ${gbp.matchReason}.` : ''
            }`
    return (
      <Alert variant={business?.gbpStatus === 'not_found' ? 'destructive' : 'default'}>
        <AlertDescription>{text}</AlertDescription>
      </Alert>
    )
  }
  const mapsHref = gbp.mapsUrl ? safeHref(gbp.mapsUrl) : null
  const links = [
    ...socials.map((s) => ({
      key: s.url,
      network: s.network,
      name: NETWORK[s.network] ?? s.network,
      href: safeHref(s.url),
    })),
    ...(website
      ? [{ key: website, network: 'website', name: 'Website', href: safeHref(website) }]
      : []),
  ].filter((l) => l.href)
  const matched = matchedOn(gbp)
  return (
    <Block title="Google Business Profile">
      <div
        className={`flex flex-col gap-3 rounded-xl bg-muted/60 p-4 ${bordered ? 'border border-border' : ''}`}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h4 className="min-w-0 break-words text-lg font-semibold leading-snug text-foreground">
            {gbp.name}
          </h4>
          {gbp.verified ? (
            <Badge variant="secondary" className="gap-1 text-[12px] font-medium normal-case">
              <BadgeCheck className="size-3.5" aria-hidden="true" />
              Verified
            </Badge>
          ) : null}
        </div>
        {matched ? <p className="text-[13px] leading-5 text-foreground/75">{matched}</p> : null}
        {gbp.primaryCategory ? (
          <p>
            <span className="inline-block rounded-full bg-accent-wcm px-3 py-1 text-[13px] font-semibold text-white">
              {gbp.primaryCategory}
            </span>
          </p>
        ) : null}
        {links.length ? (
          <ul className="flex flex-wrap gap-2">
            {links.map((l) => (
              <li key={l.key}>
                <a
                  href={l.href ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  title={l.name}
                  aria-label={`${l.name} (opens in a new tab)`}
                  className="block rounded-lg transition-opacity hover:opacity-80 focus-visible:outline-2 focus-visible:outline-ring"
                >
                  <SocialIcon network={l.network} />
                </a>
              </li>
            ))}
          </ul>
        ) : null}
        <StaticMap
          href={mapsHref}
          label={`Map of ${gbp.name ?? 'the business'} (opens Google Maps)`}
        />
        <ul className="flex flex-col gap-1 text-[14px] text-foreground">
          {gbp.address ? (
            <li className="flex items-center gap-2">
              <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1">{gbp.address}</span>
              <CopyButton text={gbp.address} label="address" />
            </li>
          ) : null}
          {gbp.phone ? (
            <li className="flex items-center gap-2">
              <Phone className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 tabular-nums">{gbp.phone}</span>
              <CopyButton text={gbp.phone} label="phone number" />
            </li>
          ) : null}
          {gbp.rating != null ? (
            <li className="flex items-center gap-2">
              <Star
                className="size-4 shrink-0 fill-accent-wcm text-accent-wcm"
                aria-hidden="true"
              />
              <span className="tabular-nums">
                <span className="font-semibold">{gbp.rating}</span>
                {gbp.reviewCount != null ? (
                  <span className="text-muted-foreground">
                    {' '}
                    ({gbp.reviewCount.toLocaleString()} Google reviews)
                  </span>
                ) : null}
              </span>
            </li>
          ) : null}
        </ul>
        {mapsHref ? (
          <a
            href={mapsHref}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 self-start text-[14px] font-medium text-primary underline underline-offset-2"
          >
            <Globe className="size-4" aria-hidden="true" />
            Open Google Business Profile
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        ) : null}
      </div>
      {business ? <ProfileSignals business={business} /> : null}
    </Block>
  )
}

type SignalTone = 'good' | 'warn' | 'bad' | 'neutral'
const SIGNAL_TONE: Record<SignalTone, string> = {
  good: 'bg-success/15 text-success',
  warn: 'bg-accent-wcm/15 text-accent-wcm',
  bad: 'bg-destructive/10 text-destructive',
  neutral: 'bg-muted text-muted-foreground',
}

/** One profile check: the label, what to do when it fails, and the result as a pill. */
export function ProfileSignals({ business }: { business: BusinessSection }) {
  const gbp = business.gbp
  if (!gbp?.matched) return null
  const nap = business.nap.consistentWithGbp
  const signals: { label: string; hint: string; tone: SignalTone; value: string }[] = [
    {
      label: 'Website links to Google profile',
      value: gbp.websiteLinksToGbp ? 'Linked' : 'Not found',
      tone: gbp.websiteLinksToGbp ? 'good' : 'warn',
      hint: 'No link to the Google profile was found on the pages we read. Add one to the footer.',
    },
    {
      label: 'Review link on site',
      value: gbp.reviewLinkOnSite ? 'Linked' : 'Not found',
      tone: gbp.reviewLinkOnSite ? 'good' : 'warn',
      hint: 'No “leave a review” link to Google was found. Add a button that opens the Google review form.',
    },
    {
      label: 'Phone matches Google',
      value: nap == null ? 'Not compared' : nap ? 'Matches' : 'Differs',
      tone: nap == null ? 'neutral' : nap ? 'good' : 'bad',
      hint: 'The phone number on the website is different from the one on Google.',
    },
  ]
  return (
    <ul className="mt-3 divide-y divide-border/70 rounded-xl border border-border px-3">
      {signals.map((x) => (
        <li key={x.label} className="flex items-start justify-between gap-3 py-3">
          <div className="min-w-0">
            <p className="text-[14px] font-medium text-foreground">{x.label}</p>
            {x.tone === 'warn' || x.tone === 'bad' ? (
              <p className="mt-0.5 text-[13px] leading-5 text-foreground/75">{x.hint}</p>
            ) : null}
          </div>
          <span
            className={cn(
              'shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-semibold',
              SIGNAL_TONE[x.tone],
            )}
          >
            {x.value}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function CompanyCard({ company }: { company: BusinessSection['company'] }) {
  if (!company) return null
  const { employeeCount, estimatedRevenue, linkedinUrl, foundedYear } = company
  return (
    <Block title="Company (Apollo)">
      {company.description ? <Row label="Description">{company.description}</Row> : null}
      {company.industry ? <Row label="Industry">{company.industry}</Row> : null}
      {employeeCount != null ? <Row label="Employees">{employeeCount}</Row> : null}
      {foundedYear ? <Row label="Founded">{foundedYear}</Row> : null}
      {company.phone ? <Row label="Phone">{company.phone}</Row> : null}
      {company.address ? <Row label="Address">{company.address}</Row> : null}
      {estimatedRevenue ? (
        <Row label="Est. revenue">${estimatedRevenue} (Apollo estimate)</Row>
      ) : null}
      {linkedinUrl ? (
        <Row label="LinkedIn">
          <ExtLink href={linkedinUrl}>Company page</ExtLink>
        </Row>
      ) : null}
      {company.keywords?.length ? (
        <ChipRow label="Focus areas" items={company.keywords.slice(0, 8)} />
      ) : null}
      {company.technologies.length ? (
        <ChipRow label="Technologies" items={company.technologies.slice(0, 12)} />
      ) : null}
    </Block>
  )
}

export function BusinessTab({
  business,
  audit,
  website = null,
  bordered = false,
  showWebsiteActions = false,
  gbpPending = false,
  extra,
}: {
  business: BusinessSection
  audit?: Audit
  website?: string | null
  bordered?: boolean
  showWebsiteActions?: boolean
  /** While GBP is still loading, show a skeleton instead of the card. */
  gbpPending?: boolean
  /** Extra sections after company (e.g. Call Mode local competitors). */
  extra?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 [&>*+*]:border-t [&>*+*]:border-border [&>*+*]:pt-3">
      {gbpPending ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <GbpCard
          gbp={business.gbp}
          socials={business.socials}
          website={website ?? audit?.url}
          bordered={bordered}
          business={business}
        />
      )}
      {audit ? <WebsiteSummary audit={audit} showActions={showWebsiteActions} /> : null}
      {business.company ? (
        <CompanyCard company={business.company} />
      ) : audit ? (
        <Block title="Company">
          <p className="text-[14px] text-foreground/80">
            Company data is not available for this audit.
          </p>
        </Block>
      ) : null}
      {business.socials.length && !business.gbp?.matched ? (
        <Block title="Socials">
          <ul className="divide-y divide-border/70 rounded-xl border border-border">
            {business.socials.map((s) => {
              const href = safeHref(s.url)
              const handle = s.url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')
              const name = NETWORK[s.network] ?? s.network
              const row = (
                <>
                  <SocialIcon network={s.network} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-medium text-foreground">{name}</span>
                    <span className="block truncate text-[13px] text-foreground/75">{handle}</span>
                  </span>
                  <ExternalLink
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                </>
              )
              return (
                <li key={s.url}>
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`${name}: ${handle} (opens in a new tab)`}
                      className="flex items-center gap-3 px-3 py-2.5 transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {row}
                    </a>
                  ) : (
                    <div className="flex items-center gap-3 px-3 py-2.5">{row}</div>
                  )}
                </li>
              )
            })}
          </ul>
        </Block>
      ) : null}
      {extra}
    </div>
  )
}
