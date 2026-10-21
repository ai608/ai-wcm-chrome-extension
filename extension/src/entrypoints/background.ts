import { defineBackground } from 'wxt/utils/define-background'
import { classifyTab } from '@/lib/active-tab'
import { ApiError } from '@/lib/api/errors'
import * as mockApi from '@/lib/api/mock/handlers'
import * as realApi from '@/lib/api/o4'
import { getEnv, getO1WebUrl } from '@/lib/env'
import { onMessage } from '@/lib/messaging'
import { activeTabItem, authHandoffItem, authItem, authUserItem } from '@/lib/storage'

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

async function startWebSignIn() {
  const state = base64url(crypto.getRandomValues(new Uint8Array(32)))
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)))
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  const challenge = base64url(new Uint8Array(hash))
  await authHandoffItem.setValue({ state, verifier, createdAt: Date.now() })
  const url = new URL('/extension/connect', getO1WebUrl())
  url.searchParams.set('extension_id', browser.runtime.id)
  url.searchParams.set('state', state)
  url.searchParams.set('code_challenge', challenge)
  await browser.tabs.create({ url: url.toString() })
}

async function acceptWebSignIn(
  message: unknown,
  sender: chrome.runtime.MessageSender,
): Promise<{ ok: boolean }> {
  if (!sender.url || new URL(sender.url).origin !== new URL(getO1WebUrl()).origin) {
    return { ok: false }
  }
  if (!message || typeof message !== 'object') return { ok: false }
  const data = message as Record<string, unknown>
  if (data.type !== 'wcm-extension-handoff' || typeof data.code !== 'string') {
    return { ok: false }
  }
  const pending = await authHandoffItem.getValue()
  if (!pending || Date.now() - pending.createdAt > 10 * 60_000 || data.state !== pending.state) {
    return { ok: false }
  }
  await authHandoffItem.setValue(null)
  try {
    const { tokens, user } = await realApi.exchangeWeb(data.code, pending.verifier)
    await authItem.setValue(tokens)
    await authUserItem.setValue(user)
    return { ok: true }
  } catch {
    return { ok: false }
  }
}

async function syncTab(tab: chrome.tabs.Tab | undefined) {
  if (tab?.id == null || !tab.active || tab.windowId == null) return
  const value = classifyTab(tab.id, tab.url ?? '', getEnv().ghlHost)
  await activeTabItem(tab.windowId).setValue(value)
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

  onMessage('connectWeb', startWebSignIn)

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

  onMessage('startAudit', async ({ data }) => {
    try {
      return await api.startAudit(data.url, data.force)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('getAudit', async ({ data }) => {
    try {
      return await api.getAudit(data.auditId)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('getLatestAudit', async ({ data }) => {
    try {
      return await api.getLatestAudit(data.domain)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('runDomainOverview', async ({ data }) => {
    try {
      return await api.runDomainOverview(data.auditId)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('runLocalCompetitors', async ({ data }) => {
    try {
      return await api.runLocalCompetitors(data.auditId, data.query, data.location)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('runAiVisibility', async ({ data }) => {
    try {
      return await api.runAiVisibility(data.auditId, data.prompts)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('getReport', async ({ data }) => {
    try {
      return await api.getReport(data.auditId)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('sendReport', async ({ data }) => {
    try {
      return await api.sendReport(data.auditId, data.email, data.note)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('getContactResearch', async ({ data }) => {
    try {
      return await api.getContactResearch(data.contactId)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('startContactResearch', async ({ data }) => {
    try {
      return await api.startContactResearch(data.contactId, data.force)
    } catch (err) {
      serializeError(err)
    }
  })
  onMessage('openReport', async ({ data }) => {
    await browser.tabs.create({
      url: browser.runtime.getURL(
        `/report.html?audit=${encodeURIComponent(data.auditId)}` as never,
      ),
    })
  })
}

async function syncAllTabs() {
  const tabs = await browser.tabs.query({})
  await Promise.all(tabs.map((tab) => syncTab(tab).catch(console.error)))
}

async function init() {
  await browser.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
  await browser.sidePanel.setOptions({ path: 'sidepanel.html', enabled: true })
  // Tabs opened before install/reload/startup never fire onUpdated for us.
  await syncAllTabs()
}

function main() {
  registerApiHandlers()
  browser.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
    acceptWebSignIn(message, sender)
      .then(sendResponse)
      .catch(() => sendResponse({ ok: false }))
    return true
  })
  browser.runtime.onInstalled.addListener(() => {
    init().catch(console.error)
  })
  browser.runtime.onStartup.addListener(() => {
    init().catch(console.error)
  })

  browser.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
    if (changeInfo.url == null && changeInfo.status !== 'complete') return
    syncTab(tab).catch(console.error)
  })

  browser.tabs.onActivated.addListener((activeInfo) => {
    browser.tabs.get(activeInfo.tabId).then(syncTab).catch(console.error)
  })

  browser.windows.onFocusChanged.addListener((windowId) => {
    if (windowId < 0) return
    syncWindow(windowId).catch(console.error)
  })
}

export default defineBackground(main)
