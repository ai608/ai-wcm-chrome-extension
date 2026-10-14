import { describe, expect, it } from 'vitest'
import { asActiveContact, classifyTab } from '@/lib/active-tab'

const HOST = 'app.example.com'
const k = (url: string) => classifyTab(1, url, HOST)

describe('classifyTab', () => {
  it('classifies ghl contact vs other ghl pages', () => {
    const t = k(`https://${HOST}/v2/location/L1/contacts/detail/c1`)
    expect(t).toMatchObject({ kind: 'ghl_contact', locationId: 'L1', contactId: 'c1' })
    expect(asActiveContact(t)).toEqual({ tabId: 1, url: t.url, locationId: 'L1', contactId: 'c1' })
    expect(k(`https://${HOST}/v2/location/L1/contacts/smart_list`).kind).toBe('ghl_other')
    expect(asActiveContact(k(`https://${HOST}/`))).toBeNull()
  })

  it('classifies websites and extracts the domain', () => {
    expect(k('https://www.Glow.com/botox?x=1')).toMatchObject({
      kind: 'website',
      domain: 'glow.com',
      origin: 'https://www.glow.com',
    })
    expect(k('https://book.glow.com:8443/a').domain).toBe('book.glow.com')
    expect(k('http://localhost:3000/').kind).toBe('website')
    expect(k('https://bücher.example/').domain).toBe('xn--bcher-kva.example')
  })

  it.each([
    'chrome://extensions',
    'about:blank',
    'file:///tmp/a.html',
    'chrome-extension://abc/page.html',
    'https://chromewebstore.google.com/detail/x',
    'https://chrome.google.com/webstore/detail/x',
    'https://example.com/menu.PDF',
    '',
    'not a url',
  ])('marks %s unsupported', (url) => {
    expect(k(url).kind).toBe('unsupported')
  })
})
