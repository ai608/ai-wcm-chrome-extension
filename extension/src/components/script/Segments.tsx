import { Fragment } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import type { Segment } from '@/lib/script/template'

export function Segments({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map((s, i) => {
        if (s.kind === 'value') {
          return (
            <strong key={i} className="font-semibold">
              {s.value}
            </strong>
          )
        }
        if (s.kind === 'missing') {
          return (
            <span key={i} className="font-medium text-destructive">
              [{s.label}]
            </span>
          )
        }
        if (s.kind === 'pending') {
          return <Skeleton key={i} className="inline-block h-3 w-16 align-middle" />
        }
        return <Fragment key={i}>{s.value}</Fragment>
      })}
    </>
  )
}
