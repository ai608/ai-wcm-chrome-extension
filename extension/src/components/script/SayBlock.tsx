import { Segments } from '@/components/script/Segments'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'
import { cn } from '@/lib/utils'

export function SayBlock({
  text,
  tone,
  ctx,
}: {
  text: string
  tone?: 'default' | 'highlight'
  ctx: TemplateCtx
}) {
  return (
    <p
      className={cn(
        'rounded-lg border border-primary/15 bg-primary/[0.06] px-3 py-2.5 text-[14px] leading-[1.55]',
        tone === 'highlight' && 'border-primary/40 bg-primary/10',
      )}
    >
      <Segments segments={renderTemplate(text, ctx)} />
    </p>
  )
}
