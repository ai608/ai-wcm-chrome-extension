import { BadgeCheck, Copy, ExternalLink, Globe, MapPin, Phone, Star } from 'lucide-react'
import { SocialIcon } from '@/components/research/SocialIcon'
import { StaticMap } from '@/components/research/StaticMap'
import { Block, Chip, ExtLink } from '@/components/research/shared'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import type { BusinessSection } from '@/lib/api/research-types'
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
}: {
  gbp: BusinessSection['gbp']
  socials?: BusinessSection['socials']
  website?: string | null
}) {
  if (!gbp?.matched) {
    return (
      <Alert>
        <AlertDescription>
          Google Business Profile data is not available for this audit.
          {gbp?.matchReason ? ` ${gbp.matchReason}.` : ''}
        </AlertDescription>
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
      <div className="flex flex-col gap-3 rounded-xl bg-muted/60 p-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h4 className="min-w-0 break-words text-lg font-semibold leading-snug text-foreground">
            {gbp.name}
          </h4>
          {gbp.verified ? (
            <Badge variant="secondary" className="gap-1 text-[11px] font-medium normal-case">
              <BadgeCheck className="size-3.5" aria-hidden="true" />
              Verified
            </Badge>
          ) : null}
        </div>
        {matched ? <p className="text-[12px] leading-5 text-muted-foreground">{matched}</p> : null}
        {gbp.primaryCategory ? (
          <p>
            <span className="inline-block rounded-full bg-accent-wcm px-3 py-1 text-[12px] font-semibold text-white">
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
    <Block title="Profile signals">
      <ul className="divide-y divide-border/70 rounded-xl border border-border px-3">
        {signals.map((x) => (
          <li key={x.label} className="flex items-start justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="text-[14px] font-medium text-foreground">{x.label}</p>
              {x.tone === 'warn' || x.tone === 'bad' ? (
                <p className="mt-0.5 text-[12px] leading-5 text-muted-foreground">{x.hint}</p>
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

export function BusinessTab({
  business,
  website = null,
}: {
  business: BusinessSection
  website?: string | null
}) {
  return (
    <div className="flex flex-col gap-3">
      <GbpCard gbp={business.gbp} socials={business.socials} website={website} />
      <ProfileSignals business={business} />
      <CompanyCard company={business.company} />
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
                    <span className="block truncate text-[12px] text-muted-foreground">
                      {handle}
                    </span>
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
    </div>
  )
}
