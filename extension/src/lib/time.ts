export function relativeTime(iso: string | null, now = Date.now()): string {
  if (!iso) return 'never'
  const diffMs = new Date(iso).getTime() - now
  const abs = Math.abs(diffMs)
  const minute = 60_000
  const hour = 3_600_000
  const day = 86_400_000
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (abs < hour) {
    const m = Math.round(diffMs / minute)
    return m === 0 ? 'just now' : rtf.format(m, 'minute')
  }
  if (abs < day) return rtf.format(Math.round(diffMs / hour), 'hour')
  if (abs < 30 * day) return rtf.format(Math.round(diffMs / day), 'day')
  if (abs < 365 * day) return rtf.format(Math.round(diffMs / (30 * day)), 'month')
  return rtf.format(Math.round(diffMs / (365 * day)), 'year')
}

/** A date the page gave us (a post's published stamp), shown as written, not shifted into the
 * viewer's time zone: 2026-10-27T20:24:40+00:00 is Oct 27 for everyone, as on the site itself. */
export function formatPostDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString(undefined, {
    dateStyle: 'medium',
    timeZone: 'UTC',
  })
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}
