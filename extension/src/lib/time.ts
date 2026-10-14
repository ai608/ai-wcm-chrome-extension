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
