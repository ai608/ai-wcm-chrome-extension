import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

const GHL_HOST = 'app.example.com'
const contactUrl = (loc: string, id: string) =>
  `https://${GHL_HOST}/v2/location/${loc}/contacts/detail/${id}`

function stubBrowser() {
  vi.stubGlobal('browser', fakeBrowser)
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

  it('enables the side panel only on ghl contact tabs', async () => {
    const { setOptions } = stubBrowser()
    await startBackground()

    await fakeBrowser.tabs.onUpdated.trigger(
      7,
      { url: contactUrl('L1', 'c_1') },
      tab({ id: 7, url: contactUrl('L1', 'c_1') }),
    )
    expect(setOptions).toHaveBeenCalledWith({
      tabId: 7,
      path: 'sidepanel.html',
      enabled: true,
    })

    await fakeBrowser.tabs.onUpdated.trigger(
      8,
      { url: 'https://example.com/' },
      tab({ id: 8, url: 'https://example.com/' }),
    )
    expect(setOptions).toHaveBeenCalledWith({ tabId: 8, enabled: false })
  })

  it('disables the panel for non-contact ghl pages', async () => {
    const { setOptions } = stubBrowser()
    await startBackground()

    await fakeBrowser.tabs.onUpdated.trigger(
      9,
      { url: `https://${GHL_HOST}/v2/location/L1/contacts/smart_list` },
      tab({ id: 9, url: `https://${GHL_HOST}/v2/location/L1/contacts/smart_list` }),
    )
    expect(setOptions).toHaveBeenCalledWith({ tabId: 9, enabled: false })
  })

  it('updates the active contact item on tab updates and activation', async () => {
    stubBrowser()
    await startBackground()
    const { activeContactItem } = await import('@/lib/storage')

    await fakeBrowser.tabs.onUpdated.trigger(
      11,
      { url: contactUrl('L9', 'c_glow') },
      tab({ id: 11, windowId: 4, active: true, url: contactUrl('L9', 'c_glow') }),
    )
    await expect(activeContactItem(4).getValue()).resolves.toEqual({
      tabId: 11,
      url: contactUrl('L9', 'c_glow'),
      locationId: 'L9',
      contactId: 'c_glow',
    })

    await fakeBrowser.tabs.onActivated.trigger({ tabId: 12, windowId: 4 })
    await expect(activeContactItem(4).getValue()).resolves.toEqual({
      tabId: 11,
      url: contactUrl('L9', 'c_glow'),
      locationId: 'L9',
      contactId: 'c_glow',
    })
  })
})
