import { Segments } from '@/components/script/Segments'
import { Card } from '@/components/ui/card'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'

export function SayBlock({
  text,
  tone,
  ctx,
}: {
  text: string
  tone?: 'default' | 'highlight'
  ctx: TemplateCtx
}) {
  const segments = renderTemplate(text, ctx)
  if (tone === 'highlight') {
    return (
      <Card className="border-primary/30 bg-primary/5 px-3 py-2 text-[13px] leading-relaxed">
        <Segments segments={segments} />
      </Card>
    )
  }
  return (
    <p className="text-[13px] leading-relaxed">
      <Segments segments={segments} />
    </p>
  )
}
