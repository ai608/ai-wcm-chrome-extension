import { defineBackground } from 'wxt/utils/define-background'
import { getEnv } from '@/lib/env'
import { parseGhlUrl } from '@/lib/ghl-url'
import { type ActiveContact, activeContactItem } from '@/lib/storage'

async function syncTab(tab: chrome.tabs.Tab | undefined) {
  const env = getEnv()
  if (tab?.id == null) return
  const tabId = tab.id
  const url = tab.url ?? ''
  const ref = parseGhlUrl(url, env.ghlHost)
  if (ref) {
    await browser.sidePanel.setOptions({ tabId, path: 'sidepanel.html', enabled: true })
  } else {
    await browser.sidePanel.setOptions({ tabId, enabled: false })
  }
  if (tab.active && tab.windowId != null) {
    const value: ActiveContact | null =
      ref == null ? null : { tabId, url, locationId: ref.locationId, contactId: ref.contactId }
    await activeContactItem(tab.windowId).setValue(value)
  }
}

async function syncWindow(windowId: number) {
  const tabs = await browser.tabs.query({ active: true, windowId })
  await syncTab(tabs[0])
}

function main() {
  browser.runtime.onInstalled.addListener(() => {
    browser.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
    browser.sidePanel.setOptions({ enabled: false }).catch(() => {})
  })

  browser.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
    if (changeInfo.url == null && changeInfo.status !== 'complete') return
    syncTab(tab).catch(() => {})
  })

  browser.tabs.onActivated.addListener((activeInfo) => {
    browser.tabs
      .get(activeInfo.tabId)
      .then(syncTab)
      .catch(() => {})
  })

  browser.windows.onFocusChanged.addListener((windowId) => {
    if (windowId < 0) return
    syncWindow(windowId).catch(() => {})
  })
}

export default defineBackground(main)
