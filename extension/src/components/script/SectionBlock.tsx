import { BookingWidget } from '@/components/script/BookingWidget'
import { DoNotBookBlock } from '@/components/script/DoNotBookBlock'
import { FaqBlock } from '@/components/script/FaqBlock'
import { OutcomeBlock } from '@/components/script/OutcomeBlock'
import { QuestionField } from '@/components/script/QuestionField'
import { RecapBlock } from '@/components/script/RecapBlock'
import { ResponseOption } from '@/components/script/ResponseOption'
import { SayBlock } from '@/components/script/SayBlock'
import { TipBlock } from '@/components/script/TipBlock'
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import type { Block, Contact, FieldValue, Section } from '@/lib/api/types'
import type { RecapRowValue } from '@/lib/script/readiness'
import type { TemplateCtx } from '@/lib/script/template'

interface SectionBlockProps {
  section: Section
  contactId: string
  contact: Contact
  ctx: TemplateCtx
  fieldValues: Record<string, FieldValue>
  recapRows: RecapRowValue[]
  missing: { fieldKey: string; label: string }[]
  bookingWidgetUrl: string
  ticked: string[]
  onToggleResponse: (blockId: string) => void
  onJumpToField: (fieldKey: string) => void
}

export function SectionBlock({
  section,
  contactId,
  contact,
  ctx,
  fieldValues,
  recapRows,
  missing,
  bookingWidgetUrl,
  ticked,
  onToggleResponse,
  onJumpToField,
}: SectionBlockProps) {
  return (
    <AccordionItem value={section.id}>
      <AccordionTrigger>{section.title}</AccordionTrigger>
      <AccordionContent>
        <div className="flex flex-col gap-3">
          {section.blocks.map((block) => (
            <BlockView
              key={block.id}
              block={block}
              contactId={contactId}
              contact={contact}
              ctx={ctx}
              fieldValues={fieldValues}
              recapRows={recapRows}
              missing={missing}
              bookingWidgetUrl={bookingWidgetUrl}
              ticked={ticked}
              onToggleResponse={onToggleResponse}
              onJumpToField={onJumpToField}
            />
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}

const warned = new Set<string>()

function BlockView({
  block,
  contactId,
  contact,
  ctx,
  fieldValues,
  recapRows,
  missing,
  bookingWidgetUrl,
  ticked,
  onToggleResponse,
  onJumpToField,
}: Omit<SectionBlockProps, 'section'> & { block: Block }) {
  switch (block.type) {
    case 'say':
      return <SayBlock text={block.text} tone={block.tone} ctx={ctx} />
    case 'tip':
      return <TipBlock text={block.text} ctx={ctx} />
    case 'response':
      return (
        <ResponseOption
          id={`${contactId}-${block.id}`}
          label={block.label}
          text={block.text}
          checked={ticked.includes(block.id)}
          onToggle={() => onToggleResponse(block.id)}
          ctx={ctx}
        />
      )
    case 'question':
      return (
        <QuestionField
          key={`${contactId}-${block.fieldKey}`}
          contactId={contactId}
          block={block}
          initialValue={fieldValues[block.fieldKey]}
        />
      )
    case 'faq':
      return <FaqBlock items={block.items} />
    case 'do_not_book':
      return <DoNotBookBlock items={block.items} />
    case 'recap':
      return (
        <RecapBlock
          rows={recapRows}
          sayItBack={block.sayItBack}
          ctx={ctx}
          onJumpToField={onJumpToField}
        />
      )
    case 'outcome':
      return (
        <OutcomeBlock
          contactId={contactId}
          contact={contact}
          outcomes={block.outcomes}
          missing={missing}
          bookingWidgetUrl={bookingWidgetUrl}
          onOpenScript={() => {
            if (missing[0]) onJumpToField(missing[0].fieldKey)
          }}
        />
      )
    case 'booking':
      return <BookingWidget widgetUrl={bookingWidgetUrl} contact={contact} />
    default: {
      const t = (block as { type: string }).type
      if (!warned.has(t)) {
        warned.add(t)
        console.warn('Unknown script block type', t)
      }
      return null
    }
  }
}
