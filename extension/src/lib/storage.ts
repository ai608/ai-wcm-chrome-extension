import { storage } from 'wxt/utils/storage'
import type { ActiveTab } from '@/lib/active-tab'
import type { AuthTokens, User } from '@/lib/api/types'

export interface ActiveContact {
  tabId: number
  url: string
  locationId: string
  contactId: string
}

export type LastTab = 'script' | 'history' | 'research'

const itemCache = new Map<number, ReturnType<typeof storage.defineItem<ActiveTab | null>>>()

export function activeTabItem(windowId: number) {
  const cached = itemCache.get(windowId)
  if (cached) return cached
  const item = storage.defineItem<ActiveTab | null>(`session:activeTab:${windowId}`, {
    fallback: null,
  })
  itemCache.set(windowId, item)
  return item
}

export const lastTabItem = storage.defineItem<LastTab>('local:lastTab', { fallback: 'script' })

export const authItem = storage.defineItem<AuthTokens | null>('session:auth', { fallback: null })

export const authUserItem = storage.defineItem<User | null>('session:authUser', { fallback: null })

export const themeItem = storage.defineItem<'light' | 'dark' | 'system'>('local:theme', {
  fallback: 'system',
})

export const lastResearchTabItem = storage.defineItem<string>('local:lastResearchTab', {
  fallback: 'overview',
})
