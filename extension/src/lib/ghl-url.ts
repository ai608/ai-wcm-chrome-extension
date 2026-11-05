export interface GhlContactRef {
  locationId: string
  contactId: string
}

/** `ghlHost` is one host or a comma-separated list (white-label plus app.gohighlevel.com). */
export function isGhlHost(ghlHost: string, host: string): boolean {
  return ghlHost.split(',').some((h) => h.trim() === host)
}

export function parseGhlUrl(url: string, ghlHost: string): GhlContactRef | null {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  if (parsed.protocol !== 'https:' || !isGhlHost(ghlHost, parsed.hostname)) return null
  const match = /^\/v2\/location\/([^/]+)\/contacts\/detail\/([^/]+)\/?$/.exec(parsed.pathname)
  if (!match) return null
  const [, locationId, contactId] = match
  if (!locationId || !contactId) return null
  let decodedLocation: string
  let decodedContact: string
  try {
    decodedLocation = decodeURIComponent(locationId)
    decodedContact = decodeURIComponent(contactId)
  } catch {
    return null
  }
  if (!decodedLocation || !decodedContact) return null
  return { locationId: decodedLocation, contactId: decodedContact }
}
