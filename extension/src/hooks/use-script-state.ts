import { useEffect, useRef, useState } from 'react'
import {
  useContactContextQuery,
  useEnrichContactMutation,
  usePersonalizedScriptQuery,
  useRegenerateScriptMutation,
  useScriptDefinitionQuery,
} from '@/hooks/queries'

const GENERATE_TIMEOUT_MS = 90_000

export function useScriptState(contactId: string) {
  const definitionQuery = useScriptDefinitionQuery(true)
  const [pollScript, setPollScript] = useState(false)
  const [pollContext, setPollContext] = useState(false)
  const [timedOut, setTimedOut] = useState(false)
  const genStart = useRef<number | null>(null)
  const autoRegen = useRef<string | null>(null)

  const contextQuery = useContactContextQuery(contactId, pollContext)
  const scriptQuery = usePersonalizedScriptQuery(contactId, pollScript)
  const enrich = useEnrichContactMutation(contactId)
  const regenerate = useRegenerateScriptMutation(contactId)

  const status = scriptQuery.data?.status
  const enrichmentStatus = contextQuery.data?.enrichment.status

  useEffect(() => {
    if (status === 'generating') {
      if (genStart.current == null) genStart.current = Date.now()
      setPollScript(true)
      const elapsed = Date.now() - (genStart.current ?? Date.now())
      const remaining = GENERATE_TIMEOUT_MS - elapsed
      if (remaining <= 0) {
        setPollScript(false)
        setTimedOut(true)
        return
      }
      const t = setTimeout(() => {
        setPollScript(false)
        setTimedOut(true)
      }, remaining)
      return () => clearTimeout(t)
    }
    genStart.current = null
    setPollScript(false)
    setTimedOut(false)
  }, [status])

  useEffect(() => {
    if (enrichmentStatus === 'enriching') setPollContext(true)
    else setPollContext(false)
  }, [enrichmentStatus])

  useEffect(() => {
    if (
      status === 'none' &&
      enrichmentStatus === 'enriched' &&
      autoRegen.current !== contactId &&
      !regenerate.isPending
    ) {
      autoRegen.current = contactId
      regenerate.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, enrichmentStatus, contactId])

  function startEnrich() {
    enrich.mutate(undefined, {
      onSuccess: () => setPollContext(true),
    })
  }

  function startRegenerate() {
    setTimedOut(false)
    genStart.current = Date.now()
    regenerate.mutate()
  }

  return {
    definition: definitionQuery.data,
    definitionPending: definitionQuery.isPending,
    definitionError: definitionQuery.error,
    context: contextQuery.data,
    contextPending: contextQuery.isPending,
    contextError: contextQuery.error,
    script: scriptQuery.data,
    scriptPending: scriptQuery.isPending,
    timedOut,
    enrichPending: enrich.isPending,
    regeneratePending: regenerate.isPending,
    startEnrich,
    startRegenerate,
  }
}
