import { Segments } from '@/components/script/Segments'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'
import { cn } from '@/lib/utils'

interface ResponseOptionProps {
  id: string
  label: string
  text: string
  checked: boolean
  onToggle: (checked: boolean) => void
  ctx: TemplateCtx
}

export function ResponseOption({ id, label, text, checked, onToggle, ctx }: ResponseOptionProps) {
  return (
    <Label
      htmlFor={id}
      className={cn(
        'flex cursor-pointer items-start gap-2 rounded-lg border border-border px-2.5 py-2',
        checked && 'border-primary/40 bg-primary/5',
      )}
    >
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onToggle(v === true)}
        className="mt-0.5"
      />
      <span className="min-w-0">
        <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className="block text-[13px] leading-relaxed">
          <Segments segments={renderTemplate(text, ctx)} />
        </span>
      </span>
    </Label>
  )
}
