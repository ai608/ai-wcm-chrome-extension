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
        'flex cursor-pointer items-start gap-2 border-l-2 border-border/80 py-0.5 pl-3',
        checked && 'border-primary bg-primary/5',
      )}
    >
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onToggle(v === true)}
        className="mt-0.5"
      />
      <span className="min-w-0">
        <span className="block mb-0.5 text-[12px] font-semibold leading-normal text-foreground">
          {label}
        </span>
        <span className="block text-[14px] font-medium leading-snug text-foreground">
          <Segments segments={renderTemplate(text, ctx)} />
        </span>
      </span>
    </Label>
  )
}
