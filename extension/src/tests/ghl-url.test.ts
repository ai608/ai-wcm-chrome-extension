import { describe, expect, it } from 'vitest'
import { parseGhlUrl } from '@/lib/ghl-url'

const HOST = 'app.example.com'
const base = (path: string) => `https://${HOST}${path}`

describe('parseGhlUrl', () => {
  it('parses a plain contact url', () => {
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/c_123'), HOST)).toEqual({
      locationId: 'LOC1',
      contactId: 'c_123',
    })
  })

  it('allows trailing slash, query string and hash', () => {
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/c_123/'), HOST)).toEqual({
      locationId: 'LOC1',
      contactId: 'c_123',
    })
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/c_123?tab=notes'), HOST)).toEqual({
      locationId: 'LOC1',
      contactId: 'c_123',
    })
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/c_123#activity'), HOST)).toEqual({
      locationId: 'LOC1',
      contactId: 'c_123',
    })
  })

  it('decodes encoded segments', () => {
    expect(parseGhlUrl(base('/v2/location/LOC%201/contacts/detail/c%2F1'), HOST)).toEqual({
      locationId: 'LOC 1',
      contactId: 'c/1',
    })
  })

  it('rejects other hosts', () => {
    expect(parseGhlUrl('https://evil.com/v2/location/LOC1/contacts/detail/c_1', HOST)).toBeNull()
    expect(
      parseGhlUrl('https://app.example.com.evil.com/v2/location/L/contacts/detail/c', HOST),
    ).toBeNull()
  })

  it('rejects non-contact ghl pages', () => {
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/smart_list'), HOST)).toBeNull()
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/'), HOST)).toBeNull()
    expect(parseGhlUrl(base('/v2/location/LOC1/contacts/detail/c_1/extra'), HOST)).toBeNull()
    expect(parseGhlUrl(base('/v2/location/LOC1/dashboard'), HOST)).toBeNull()
    expect(parseGhlUrl(base('/'), HOST)).toBeNull()
  })

  it('rejects malformed urls', () => {
    expect(parseGhlUrl('not a url', HOST)).toBeNull()
    expect(parseGhlUrl('', HOST)).toBeNull()
    expect(parseGhlUrl(`http://${HOST}/v2/location/L/contacts/detail/c`, HOST)).toBeNull()
    expect(parseGhlUrl(base('/v2/location/%E0%A4%A/contacts/detail/c'), HOST)).toBeNull()
  })
})
