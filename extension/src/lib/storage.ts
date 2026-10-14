import { storage } from 'wxt/utils/storage'

export interface ActiveContact {
  tabId: number
  url: string
  locationId: string
  contactId: string
}

export type LastTab = 'script' | 'history' | 'research'

const itemCache = new Map<number, ReturnType<typeof storage.defineItem<ActiveContact | null>>>()

export function activeContactKey(windowId: number): `session:activeContact:${number}` {
  return `session:activeContact:${windowId}`
}

export function activeContactItem(windowId: number) {
  const cached = itemCache.get(windowId)
  if (cached) return cached
  const item = storage.defineItem<ActiveContact | null>(activeContactKey(windowId), {
    fallback: null,
  })
  itemCache.set(windowId, item)
  return item
}

export const lastTabItem = storage.defineItem<LastTab>('local:lastTab', { fallback: 'script' })
