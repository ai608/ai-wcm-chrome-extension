import { useEffect, useState } from 'react'
import { type ActiveContact, activeContactItem } from '@/lib/storage'

export function useActiveContact() {
  const [contact, setContact] = useState<ActiveContact | null | undefined>(undefined)

  useEffect(() => {
    let unwatch: (() => void) | undefined
    let cancelled = false
    browser.windows.getCurrent().then((win) => {
      if (cancelled || win.id == null) return
      const item = activeContactItem(win.id)
      item.getValue().then((v) => {
        if (!cancelled) setContact(v)
      })
      unwatch = item.watch((v) => setContact(v))
    })
    return () => {
      cancelled = true
      unwatch?.()
    }
  }, [])

  return contact
}
