import type { Contact } from '@/lib/api/types'

interface BookingWidgetProps {
  widgetUrl: string
  contact: Contact
}

export function bookingUrl(widgetUrl: string, contact: Contact): string {
  const url = new URL(widgetUrl)
  const params: Record<string, string> = {
    first_name: contact.firstName,
    last_name: contact.lastName,
    email: contact.email,
    phone: contact.phone,
    company_name: contact.companyName,
  }
  for (const [key, value] of Object.entries(params)) {
    if (value.trim()) url.searchParams.set(key, value)
  }
  return url.toString()
}

export function BookingWidget({ widgetUrl, contact }: BookingWidgetProps) {
  if (widgetUrl === 'about:blank' || !URL.canParse(widgetUrl)) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border text-[13px] text-muted-foreground">
        {widgetUrl === 'about:blank' ? 'Booking widget (mock)' : 'Booking widget not configured'}
      </div>
    )
  }
  return (
    <iframe
      src={bookingUrl(widgetUrl, contact)}
      title="Book discovery call"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      referrerPolicy="no-referrer"
      className="h-[640px] w-full rounded-lg border border-border"
    />
  )
}
