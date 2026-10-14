import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

const GHL_HOST = 'app.example.com'
const contactUrl = (loc: string, id: string) =>
  `https://${GHL_HOST}/v2/location/${loc}/contacts/detail/${id}`

function stubBrowser() {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  vi.stubEnv('WXT_GHL_HOST', GHL_HOST)
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
  const setOptions = vi.fn(() => Promise.resolve())
  const setPanelBehavior = vi.fn(() => Promise.resolve())
  ;(fakeBrowser as unknown as Record<string, unknown>).sidePanel = {
    setOptions,
    setPanelBehavior,
  }
  return { setOptions, setPanelBehavior }
}

async function startBackground() {
  const mod = await import('@/entrypoints/background')
  const def = mod.default as unknown as { main: () => void }
  def.main()
}

function tab(overrides: Partial<chrome.tabs.Tab> = {}): chrome.tabs.Tab {
  return { id: 1, windowId: 1, active: true, ...overrides } as chrome.tabs.Tab
}

describe('background', () => {
  beforeEach(() => {
    fakeBrowser.reset()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('enables the panel on ghl contact tabs, disables elsewhere, tracks the active contact', async () => {
    const { setOptions, setPanelBehavior } = stubBrowser()
    await startBackground()
    const { activeTabItem } = await import('@/lib/storage')

    await fakeBrowser.runtime.onInstalled.trigger({ reason: 'install' })
    expect(setPanelBehavior).toHaveBeenCalledWith({ openPanelOnActionClick: true })

    await fakeBrowser.tabs.onUpdated.trigger(
      7,
      { url: contactUrl('L1', 'c_1') },
      tab({ id: 7, windowId: 1, active: true, url: contactUrl('L1', 'c_1') }),
    )
    expect(setOptions).toHaveBeenCalledWith({ path: 'sidepanel.html', enabled: true })
    await expect(activeTabItem(1).getValue()).resolves.toEqual({
      tabId: 7,
      url: contactUrl('L1', 'c_1'),
      kind: 'ghl_contact',
      locationId: 'L1',
      contactId: 'c_1',
    })

    await fakeBrowser.tabs.onUpdated.trigger(
      8,
      { url: 'https://example.com/' },
      tab({ id: 8, windowId: 1, active: true, url: 'https://example.com/' }),
    )
    await expect(activeTabItem(1).getValue()).resolves.toMatchObject({
      kind: 'website',
      domain: 'example.com',
    })

    const smartList = `https://${GHL_HOST}/v2/location/L1/contacts/smart_list`
    await fakeBrowser.tabs.onUpdated.trigger(
      9,
      { url: smartList },
      tab({ id: 9, windowId: 1, active: true, url: smartList }),
    )
    await expect(activeTabItem(1).getValue()).resolves.toMatchObject({ kind: 'ghl_other' })

    await fakeBrowser.tabs.onUpdated.trigger(
      11,
      { url: contactUrl('L9', 'c_glow') },
      tab({ id: 11, windowId: 4, active: true, url: contactUrl('L9', 'c_glow') }),
    )
    await expect(activeTabItem(4).getValue()).resolves.toEqual({
      tabId: 11,
      url: contactUrl('L9', 'c_glow'),
      kind: 'ghl_contact',
      locationId: 'L9',
      contactId: 'c_glow',
    })

    await fakeBrowser.tabs.onActivated.trigger({ tabId: 12, windowId: 4 })
    await expect(activeTabItem(4).getValue()).resolves.toEqual({
      tabId: 11,
      url: contactUrl('L9', 'c_glow'),
      kind: 'ghl_contact',
      locationId: 'L9',
      contactId: 'c_glow',
    })
  })
})
