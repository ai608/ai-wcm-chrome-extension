import { DoNotBookBlock } from '@/components/script/DoNotBookBlock'
import { FaqBlock } from '@/components/script/FaqBlock'
import { QuestionField } from '@/components/script/QuestionField'
import { ResponseOption } from '@/components/script/ResponseOption'
import { SayBlock } from '@/components/script/SayBlock'
import { TipBlock } from '@/components/script/TipBlock'
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import type { Block, FieldValue, Section } from '@/lib/api/types'
import type { TemplateCtx } from '@/lib/script/template'

interface SectionBlockProps {
  section: Section
  contactId: string
  ctx: TemplateCtx
  fieldValues: Record<string, FieldValue>
  ticked: string[]
  onToggleResponse: (blockId: string) => void
}

export function SectionBlock({
  section,
  contactId,
  ctx,
  fieldValues,
  ticked,
  onToggleResponse,
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
              ctx={ctx}
              fieldValues={fieldValues}
              ticked={ticked}
              onToggleResponse={onToggleResponse}
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
  ctx,
  fieldValues,
  ticked,
  onToggleResponse,
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
    case 'outcome':
    case 'booking':
      return null
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
