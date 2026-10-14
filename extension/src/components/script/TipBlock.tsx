import { Lightbulb } from 'lucide-react'
import { Segments } from '@/components/script/Segments'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'

export function TipBlock({ text, ctx }: { text: string; ctx: TemplateCtx }) {
  return (
    <Alert className="border-amber-500/40 bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
      <Lightbulb className="size-4" />
      <AlertDescription className="text-[13px]">
        <Segments segments={renderTemplate(text, ctx)} />
      </AlertDescription>
    </Alert>
  )
}
