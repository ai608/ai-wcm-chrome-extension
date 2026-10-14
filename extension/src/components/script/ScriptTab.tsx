import { useMemo } from 'react'
import { SectionBlock } from '@/components/script/SectionBlock'
import { Accordion } from '@/components/ui/accordion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { useScriptState } from '@/hooks/use-script-state'
import { computeRecap, missingForBooking } from '@/lib/script/readiness'
import type { TemplateCtx } from '@/lib/script/template'
import { relativeTime } from '@/lib/time'
import { usePanelStore } from '@/stores/panel-store'

interface ScriptTabProps {
  contactId: string
  callerFirstName: string
  bookingWidgetUrl: string
  state: ReturnType<typeof useScriptState>
}

export function ScriptTab({ contactId, callerFirstName, bookingWidgetUrl, state }: ScriptTabProps) {
  const {
    definition,
    definitionPending,
    definitionError,
    context,
    contextPending,
    contextError,
    script,
    scriptPending,
    timedOut,
    enrichPending,
    regeneratePending,
    startEnrich,
    startRegenerate,
  } = state

  const openSections = usePanelStore((s) => s.openSections)
  const setSectionOpen = usePanelStore((s) => s.setSectionOpen)
  const ticked = usePanelStore((s) => s.tickedResponses[contactId] ?? [])
  const toggleResponse = usePanelStore((s) => s.toggleResponse)

  if (definitionPending || contextPending || scriptPending) {
    return (
      <div className="flex flex-col gap-2" aria-label="Loading script">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (definitionError || !definition) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Couldn&apos;t load the call script.</AlertDescription>
      </Alert>
    )
  }

  if (contextError || !context) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Contact not found in GHL</AlertDescription>
      </Alert>
    )
  }

  const status = script?.status ?? 'none'
  const enriched = context.enrichment.status === 'enriched'
  const slotsPending = status === 'generating' || (status === 'none' && enriched)

  const recap = useMemo(
    () => computeRecap(definition, context),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [definition, context.fieldValues, context.contact],
  )
  const missing = useMemo(
    () => missingForBooking(definition, context.fieldValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [definition, context.fieldValues],
  )

  const ctx: TemplateCtx = {
    contact: context.contact,
    fields: context.fieldValues,
    computed: recap.computed,
    slots: script?.slots ?? {},
    slotsPending,
    omitAi: status === 'none' && !enriched,
    callerFirstName,
  }

  function jumpToField(fieldKey: string) {
    const section = definition?.sections.find((s) =>
      s.blocks.some((b) => b.type === 'question' && b.fieldKey === fieldKey),
    )
    if (section) setSectionOpen(section.id, true)
    requestAnimationFrame(() => {
      const el = document.querySelector(
        `[data-field="${CSS.escape(fieldKey)}"] input, [data-field="${CSS.escape(fieldKey)}"] textarea, [data-field="${CSS.escape(fieldKey)}"] button, [data-field="${CSS.escape(fieldKey)}"] [role="radio"]`,
      )
      if (el) {
        el.scrollIntoView({ block: 'center' })
        ;(el as HTMLElement).focus()
      }
    })
  }

  const openIds = definition.sections
    .filter((s) => openSections[s.id] ?? s.defaultOpen)
    .map((s) => s.id)

  return (
    <div className="flex flex-col gap-3">
      {status === 'generating' && !timedOut ? (
        <p className="text-xs text-muted-foreground">Personalizing script…</p>
      ) : null}
      {timedOut ? (
        <Alert>
          <AlertDescription className="flex items-center gap-2">
            <span className="flex-1">Still generating…</span>
            <Button
              variant="outline"
              size="xs"
              onClick={startRegenerate}
              disabled={regeneratePending}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {status === 'failed' ? (
        <Alert variant="destructive">
          <AlertDescription className="flex items-center gap-2">
            <span className="flex-1">
              Personalization failed{script?.error ? `: ${script.error}` : ''}
            </span>
            <Button
              variant="outline"
              size="xs"
              onClick={startRegenerate}
              disabled={regeneratePending}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {status === 'none' && !enriched ? (
        <Alert>
          <AlertDescription className="flex items-center gap-2">
            <span className="flex-1">This prospect hasn&apos;t been enriched yet.</span>
            <Button size="xs" onClick={startEnrich} disabled={enrichPending}>
              {enrichPending || context.enrichment.status === 'enriching'
                ? 'Enriching…'
                : 'Enrich this prospect'}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      <Accordion
        multiple
        value={openIds}
        onValueChange={(ids) => {
          for (const s of definition.sections) setSectionOpen(s.id, ids.includes(s.id))
        }}
      >
        {definition.sections.map((section) => (
          <SectionBlock
            key={section.id}
            section={section}
            contactId={contactId}
            contact={context.contact}
            ctx={ctx}
            fieldValues={context.fieldValues}
            recapRows={recap.rows}
            missing={missing}
            bookingWidgetUrl={bookingWidgetUrl}
            ticked={ticked}
            onToggleResponse={(blockId) => toggleResponse(contactId, blockId)}
            onJumpToField={jumpToField}
          />
        ))}
      </Accordion>
      <p className="text-[11px] text-muted-foreground">
        Script v{definition.version}
        {script?.generatedAt ? ` · personalized ${relativeTime(script.generatedAt)}` : ''}
      </p>
    </div>
  )
}
