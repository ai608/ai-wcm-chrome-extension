import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '@/lib/api/errors'
import { type Audit, auditBusy } from '@/lib/api/research-types'
import { call } from '@/lib/messaging'

export const POLL_MS = 2000
export const POLL_CAP_MS = 3 * 60_000

export const rk = {
  audit: (id: string) => ['audit', id] as const,
  latest: (domain: string) => ['audit-latest', domain] as const,
  contact: (id: string) => ['contact', id, 'research'] as const,
  report: (id: string) => ['report', id] as const,
}

const retryRule = (count: number, err: unknown) =>
  count < 1 && !(err instanceof ApiError && err.status >= 400 && err.status < 500)

/** Poll interval while busy, stopping after POLL_CAP_MS. Returns [interval, timedOut]. */
export function usePollWindow(busy: boolean): [number | false, boolean] {
  const [timedOut, setTimedOut] = useState(false)
  const started = useRef<number | null>(null)
  useEffect(() => {
    if (!busy) {
      started.current = null
      setTimedOut(false)
      return
    }
    if (started.current == null) started.current = Date.now()
    const t = setTimeout(
      () => setTimedOut(true),
      Math.max(0, POLL_CAP_MS - (Date.now() - started.current)),
    )
    return () => clearTimeout(t)
  }, [busy])
  return [busy && !timedOut ? POLL_MS : false, busy && timedOut]
}

export function useLatestAudit(domain: string | undefined) {
  const client = useQueryClient()
  const key = rk.latest(domain ?? '')
  const query = useQuery({
    queryKey: key,
    queryFn: () => call('getLatestAudit', { domain: domain as string }),
    enabled: !!domain,
    retry: retryRule,
  })
  const busy = auditBusy(query.data)
  const [interval, timedOut] = usePollWindow(busy)
  // poll by id so mutations on the audit land in the same cache entry
  const id = query.data?.id
  const poll = useQuery({
    queryKey: rk.audit(id ?? ''),
    queryFn: async () => {
      const a = await call('getAudit', { auditId: id as string })
      client.setQueryData(key, a)
      return a
    },
    enabled: !!id && busy,
    refetchInterval: interval,
    retry: retryRule,
  })
  return { audit: (poll.data ?? query.data) as Audit | null | undefined, query, key, timedOut }
}

export function useStartAudit(domain: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { url: string; force?: boolean }) => call('startAudit', input),
    onSuccess: (a) => client.setQueryData(rk.latest(domain), a),
  })
}

type OnDemandCall =
  | { kind: 'domain' }
  | { kind: 'local'; query?: string; location?: string }
  | { kind: 'ai'; prompts: string[] }

export function useRunOnDemand(auditId: string, domain: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (c: OnDemandCall) =>
      c.kind === 'domain'
        ? call('runDomainOverview', { auditId })
        : c.kind === 'local'
          ? call('runLocalCompetitors', { auditId, query: c.query, location: c.location })
          : call('runAiVisibility', { auditId, prompts: c.prompts }),
    onSuccess: (a) => {
      client.setQueryData(rk.latest(domain), a)
      client.setQueryData(rk.audit(auditId), a)
    },
  })
}

export function useSendReport(auditId: string) {
  return useMutation({
    mutationFn: (input: { email: string; note?: string }) =>
      call('sendReport', { auditId, ...input }),
  })
}

export function useContactResearch(contactId: string) {
  const client = useQueryClient()
  const key = rk.contact(contactId)
  const query = useQuery({
    queryKey: key,
    queryFn: () => call('getContactResearch', { contactId }),
    retry: retryRule,
  })
  const audit = query.data?.audit ?? null
  const busy = auditBusy(audit)
  const [interval, timedOut] = usePollWindow(busy)
  useQuery({
    queryKey: rk.audit(audit?.id ?? ''),
    queryFn: async () => {
      const a = await call('getAudit', { auditId: audit?.id as string })
      client.setQueryData(key, { audit: a })
      return a
    },
    enabled: !!audit && busy,
    refetchInterval: interval,
    retry: retryRule,
  })
  const start = useMutation({
    mutationFn: (force?: boolean) => call('startContactResearch', { contactId, force }),
    onSuccess: (r) => client.setQueryData(key, r),
  })
  return { query, audit, start, timedOut }
}

export function useReport(auditId: string | null) {
  return useQuery({
    queryKey: rk.report(auditId ?? ''),
    queryFn: () => call('getReport', { auditId: auditId as string }),
    enabled: !!auditId,
    retry: retryRule,
  })
}
