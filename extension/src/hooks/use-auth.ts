import { useEffect, useState } from 'react'
import { queryClient } from '@/app/providers'
import type { User } from '@/lib/api/types'
import { call } from '@/lib/messaging'
import { authUserItem } from '@/lib/storage'
import { resetAutosave } from '@/stores/autosave-store'

export function useAuth() {
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    let unwatch: (() => void) | undefined
    let cancelled = false
    authUserItem.getValue().then((v) => {
      if (!cancelled) setUser(v)
    })
    unwatch = authUserItem.watch((v, previous) => {
      if (v?.id !== previous?.id) {
        resetAutosave()
        queryClient.clear()
      }
      setUser(v)
    })
    return () => {
      cancelled = true
      unwatch?.()
    }
  }, [])

  return { user, isLoading: user === undefined }
}

export function login(email: string, password: string, totpCode?: string) {
  return call('login', { email, password, totpCode })
}

export function logout() {
  return call('logout')
}
