import { Lightbulb } from 'lucide-react'
import { Segments } from '@/components/script/Segments'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'

export function TipBlock({ text, ctx }: { text: string; ctx: TemplateCtx }) {
  return (
    <Alert className="border-amber-500/40 bg-amber-50 text-amber-900">
      <Lightbulb className="size-4" />
      <AlertDescription className="text-xs">
        <Segments segments={renderTemplate(text, ctx)} />
      </AlertDescription>
    </Alert>
  )
}
