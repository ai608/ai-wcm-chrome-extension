import { defineBackground } from 'wxt/utils/define-background'
import { ApiError } from '@/lib/api/errors'
import * as mockApi from '@/lib/api/mock/handlers'
import * as realApi from '@/lib/api/o4'
import { getEnv } from '@/lib/env'
import { parseGhlUrl } from '@/lib/ghl-url'
import { onMessage } from '@/lib/messaging'
import { type ActiveContact, activeContactItem, authItem, authUserItem } from '@/lib/storage'

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

function serializeError(err: unknown): never {
  if (err instanceof ApiError) throw err.toJSON()
  throw err
}

function registerApiHandlers() {
  const env = getEnv()
  const api = env.apiMock ? mockApi : realApi

  onMessage('login', async ({ data }) => {
    try {
      const { tokens, user } = await api.login(data.email, data.password, data.totpCode)
      await authItem.setValue(tokens)
      await authUserItem.setValue(user)
      return user
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('logout', async () => {
    try {
      await api.logout()
    } catch {
      // ignore logout failure
    }
    await authItem.setValue(null)
    await authUserItem.setValue(null)
  })

  onMessage('getConfig', async () => {
    try {
      return await api.getConfig()
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('getScriptDefinition', async () => {
    try {
      return await api.getScriptDefinition()
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('getContactContext', async ({ data }) => {
    try {
      return await api.getContactContext(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('getPersonalizedScript', async ({ data }) => {
    try {
      return await api.getPersonalizedScript(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('regenerateScript', async ({ data }) => {
    try {
      return await api.regenerateScript(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('patchFields', async ({ data }) => {
    try {
      return await api.patchFields(data.contactId, data.fields)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('saveOutcome', async ({ data }) => {
    try {
      return await api.saveOutcome(data.contactId, data.outcomeId, data.note, data.booked)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('enrichContact', async ({ data }) => {
    try {
      return await api.enrichContact(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })

  onMessage('getHistory', async ({ data }) => {
    try {
      return await api.getHistory(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })
}

function main() {
  registerApiHandlers()
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
