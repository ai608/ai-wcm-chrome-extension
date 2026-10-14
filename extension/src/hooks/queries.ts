import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from '@/components/ui/toast'
import { ApiError } from '@/lib/api/errors'
import { call } from '@/lib/messaging'

export const qk = {
  config: ['config'],
  scriptDefinition: ['script-definition'],
  contactContext: (contactId: string) => ['contact', contactId, 'context'],
  contactScript: (contactId: string) => ['contact', contactId, 'script'],
  contactHistory: (contactId: string) => ['contact', contactId, 'history'],
} as const

function retryRule(count: number, err: unknown) {
  return count < 1 && !(err instanceof ApiError && err.status >= 400 && err.status < 500)
}

export function useConfigQuery(enabled: boolean) {
  return useQuery({
    queryKey: qk.config,
    queryFn: () => call('getConfig'),
    staleTime: Number.POSITIVE_INFINITY,
    enabled,
    retry: retryRule,
  })
}

export function useScriptDefinitionQuery(enabled: boolean) {
  return useQuery({
    queryKey: qk.scriptDefinition,
    queryFn: () => call('getScriptDefinition'),
    staleTime: Number.POSITIVE_INFINITY,
    enabled,
    retry: retryRule,
  })
}

export function useContactContextQuery(contactId: string, pollEnrichment = false) {
  return useQuery({
    queryKey: qk.contactContext(contactId),
    queryFn: () => call('getContactContext', { contactId }),
    refetchInterval: pollEnrichment ? 3000 : false,
    retry: retryRule,
  })
}

export function usePersonalizedScriptQuery(contactId: string, generating = false) {
  return useQuery({
    queryKey: qk.contactScript(contactId),
    queryFn: () => call('getPersonalizedScript', { contactId }),
    refetchInterval: generating ? 3000 : false,
    retry: retryRule,
  })
}

export function useHistoryQuery(contactId: string) {
  return useQuery({
    queryKey: qk.contactHistory(contactId),
    queryFn: () => call('getHistory', { contactId }),
    staleTime: 60_000,
    retry: retryRule,
  })
}

export function useRefreshContact() {
  const client = useQueryClient()
  return (contactId: string) => client.invalidateQueries({ queryKey: ['contact', contactId] })
}

export function useRegenerateScriptMutation(contactId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => call('regenerateScript', { contactId }),
    onSuccess: (data) => {
      client.setQueryData(qk.contactScript(contactId), data)
      toast('Regenerating script')
    },
  })
}

export function useEnrichContactMutation(contactId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => call('enrichContact', { contactId }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.contactContext(contactId) })
      client.invalidateQueries({ queryKey: qk.contactScript(contactId) })
    },
  })
}

export function useSaveOutcomeMutation(contactId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { outcomeId: string; note: string; booked: boolean }) =>
      call('saveOutcome', { contactId, ...input }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: qk.contactHistory(contactId) })
    },
  })
}
