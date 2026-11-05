import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { AiUsage } from '@/lib/api/types'
import { call } from '@/lib/messaging'

const KEY = ['ai-usage'] as const

/**
 * OpenRouter spend of all users, for Settings. Only ask when `enabled` (owners and admins):
 * the server refuses everyone else. It is cached for a minute on the server, so `refresh`
 * is the way to read it again sooner.
 */
export function useAiUsage(enabled: boolean) {
  const client = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const query = useQuery({
    queryKey: KEY,
    queryFn: () => call('getAiUsage', {}),
    enabled,
    staleTime: 60_000,
    retry: false,
  })
  async function refresh() {
    setRefreshing(true)
    try {
      client.setQueryData<AiUsage>(KEY, await call('getAiUsage', { refresh: true }))
    } finally {
      setRefreshing(false)
    }
  }
  return { ...query, refresh, refreshing }
}
