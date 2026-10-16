import { ResponseOption } from '@/components/script/ResponseOption'
import { Segments } from '@/components/script/Segments'
import type { FlowNode } from '@/lib/api/types'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'

interface FlowBlockProps {
  node: FlowNode
  contactId: string
  ticked: string[]
  onToggle: (id: string) => void
  ctx: TemplateCtx
}

/** The rep's next question, the prospect's possible answers, and (once an answer is ticked) what comes next. */
export function FlowBlock({ node, contactId, ticked, onToggle, ctx }: FlowBlockProps) {
  return (
    <div className="ml-3 flex flex-col gap-2 border-l-2 border-primary/30 pl-3">
      {node.ask ? (
        <p className="text-[14px] font-semibold leading-snug text-foreground">
          <Segments segments={renderTemplate(node.ask, ctx)} />
        </p>
      ) : null}
      {node.options.map((o) => {
        const checked = ticked.includes(o.id)
        return (
          <div key={o.id} className="flex flex-col gap-2">
            <ResponseOption
              id={`${contactId}-${o.id}`}
              label={o.label}
              text={o.say}
              checked={checked}
              onToggle={() => onToggle(o.id)}
              ctx={ctx}
            />
            {checked && o.next ? (
              <FlowBlock
                node={o.next}
                contactId={contactId}
                ticked={ticked}
                onToggle={onToggle}
                ctx={ctx}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
