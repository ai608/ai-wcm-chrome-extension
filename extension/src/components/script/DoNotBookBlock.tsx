import { Card } from '@/components/ui/card'

export function DoNotBookBlock({ items }: { items: string[] }) {
  return (
    <Card className="border-destructive/40 bg-destructive/5 px-3 py-2">
      <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-destructive">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </Card>
  )
}
