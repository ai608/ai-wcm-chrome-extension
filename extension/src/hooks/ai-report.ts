import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { rk } from '@/hooks/research-queries'
import type { Audit } from '@/lib/api/research-types'
import { call } from '@/lib/messaging'
import { useAiDraft } from '@/stores/ai-draft-store'

/** Step 1: write the questions. The user reviews them before anything is paid for. */
export function useAiQuestions(auditId: string) {
  return useMutation({
    mutationFn: () => call('getAiQuestions', { auditId }),
    // Here, not in mutate(): this still runs if the user switched tabs while the questions were
    // being written, so they are not lost.
    onSuccess: (plan) => useAiDraft.getState().setDraft(auditId, { list: plan.prompts, plan }),
  })
}

/** Step 2: start the full AI visibility report with the approved questions. The job runs on the server; the audit poll shows it. */
export function useRunAiReport(auditId: string, domain: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (prompts?: string[]) => call('runAiReport', { auditId, prompts }),
    onSuccess: (a: Audit) => {
      useAiDraft.getState().clearDraft(auditId) // approved and started: the draft is spent
      client.setQueryData(rk.latest(domain), a)
      client.setQueryData(rk.audit(auditId), a)
      client.setQueriesData<{ audit: Audit | null }>({ queryKey: ['contact'] }, (current) =>
        current?.audit?.id === auditId ? { ...current, audit: a } : current,
      )
    },
  })
}

/** Saved answers of one report, for one engine and/or one question. Fetched only when asked for. */
export function useAiRunAnswers(
  runId: string | undefined,
  filter: { engine?: string; prompt?: number },
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['ai-run-answers', runId, filter.engine ?? null, filter.prompt ?? null],
    queryFn: () => call('getAiRunAnswers', { runId: runId as string, ...filter }),
    enabled: enabled && !!runId,
    staleTime: Number.POSITIVE_INFINITY, // saved answers never change
  })
}
