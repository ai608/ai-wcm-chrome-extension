import { isGhlHost, parseGhlUrl } from '@/lib/ghl-url'

export type TabKind = 'ghl_contact' | 'ghl_other' | 'website' | 'report' | 'unsupported'

/** Side panel asks the open report tab to save a PDF (direct download, no print dialog). */
export const REPORT_PRINT_TYPE = 'wcm-report-pdf'

/** Side panel asks the open report tab for its page as HTML (for a public link). */
export const REPORT_SNAPSHOT_TYPE = 'wcm-report-snapshot'

export interface ActiveTab {
  tabId: number
  url: string
  kind: TabKind
  locationId?: string
  contactId?: string
  origin?: string
  domain?: string
  auditId?: string
}

const STORE_HOSTS = new Set(['chrome.google.com', 'chromewebstore.google.com'])

export function classifyTab(tabId: number, url: string, ghlHost: string): ActiveTab {
  const base = { tabId, url }
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return { ...base, kind: 'unsupported' }
  }
  if (parsed.protocol === 'chrome-extension:' && parsed.pathname.endsWith('/report.html')) {
    const auditId = parsed.searchParams.get('audit')
    if (auditId) return { ...base, kind: 'report', auditId }
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { ...base, kind: 'unsupported' }
  }
  const host = parsed.hostname.toLowerCase()
  if (isGhlHost(ghlHost, host)) {
    const ref = parseGhlUrl(url, ghlHost)
    return ref ? { ...base, kind: 'ghl_contact', ...ref } : { ...base, kind: 'ghl_other' }
  }
  if (
    (STORE_HOSTS.has(host) && parsed.pathname.startsWith('/webstore')) ||
    host === 'chromewebstore.google.com' ||
    parsed.pathname.toLowerCase().endsWith('.pdf')
  ) {
    return { ...base, kind: 'unsupported' }
  }
  return { ...base, kind: 'website', origin: parsed.origin, domain: host.replace(/^www\./, '') }
}

export function asActiveContact(tab: ActiveTab | null | undefined) {
  if (tab?.kind !== 'ghl_contact' || !tab.locationId || !tab.contactId) return null
  return { tabId: tab.tabId, url: tab.url, locationId: tab.locationId, contactId: tab.contactId }
}
