import { Segments } from '@/components/script/Segments'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import type { RecapRowValue } from '@/lib/script/readiness'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'

interface RecapBlockProps {
  rows: RecapRowValue[]
  sayItBack: string
  ctx: TemplateCtx
  onJumpToField: (fieldKey: string) => void
}

export function RecapBlock({ rows, sayItBack, ctx, onJumpToField }: RecapBlockProps) {
  return (
    <div className="flex flex-col gap-2">
      <Card className="px-3 py-2">
        <div className="flex flex-col gap-1">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-2 text-xs">
              <span className="text-muted-foreground">{row.label}</span>
              {row.value != null ? (
                <span className="text-right font-medium">{row.value}</span>
              ) : (
                <span className="flex items-center gap-1">
                  <span className="font-medium text-destructive">missing</span>
                  {row.fieldKey ? (
                    <Button
                      variant="link"
                      size="xs"
                      className="h-auto p-0 text-[11px]"
                      onClick={() => onJumpToField(row.fieldKey as string)}
                    >
                      change
                    </Button>
                  ) : null}
                </span>
              )}
            </div>
          ))}
        </div>
      </Card>
      <Card className="border-primary/30 bg-primary/5 px-3 py-2 text-[13px] leading-relaxed">
        <Segments segments={renderTemplate(sayItBack, ctx)} />
      </Card>
    </div>
  )
}
