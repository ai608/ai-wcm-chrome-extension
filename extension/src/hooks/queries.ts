import { useQuery } from '@tanstack/react-query'
import { ApiError } from '@/lib/api/errors'
import { call } from '@/lib/messaging'

export const qk = {
  config: ['config'],
} as const

export function useConfigQuery(enabled: boolean) {
  return useQuery({
    queryKey: qk.config,
    queryFn: () => call('getConfig'),
    staleTime: Number.POSITIVE_INFINITY,
    enabled,
    retry: (count, err) =>
      count < 1 && !(err instanceof ApiError && err.status >= 400 && err.status < 500),
  })
}
