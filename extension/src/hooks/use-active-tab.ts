import { useEffect, useState } from 'react'
import type { ActiveTab } from '@/lib/active-tab'
import { activeTabItem } from '@/lib/storage'

export function useActiveTab() {
  const [tab, setTab] = useState<ActiveTab | null | undefined>(undefined)

  useEffect(() => {
    let unwatch: (() => void) | undefined
    let cancelled = false
    browser.windows.getCurrent().then((win) => {
      if (cancelled || win.id == null) return
      const item = activeTabItem(win.id)
      item.getValue().then((v) => {
        if (!cancelled) setTab(v)
      })
      unwatch = item.watch((v) => setTab(v))
    })
    return () => {
      cancelled = true
      unwatch?.()
    }
  }, [])

  return tab
}
