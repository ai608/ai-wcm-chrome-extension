export interface GhlContactRef {
  locationId: string
  contactId: string
}

export function parseGhlUrl(url: string, ghlHost: string): GhlContactRef | null {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  if (parsed.protocol !== 'https:' || parsed.hostname !== ghlHost) return null
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
