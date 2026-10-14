import { Progress as ProgressPrimitive } from '@base-ui/react/progress'
import { cn } from '@/lib/utils'

function Progress({
  className,
  indicatorClassName,
  value,
  ...props
}: ProgressPrimitive.Root.Props & { indicatorClassName?: string }) {
  return (
    <ProgressPrimitive.Root value={value} {...props}>
      <ProgressPrimitive.Track
        className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      >
        <ProgressPrimitive.Indicator className={cn('h-full bg-primary', indicatorClassName)} />
      </ProgressPrimitive.Track>
    </ProgressPrimitive.Root>
  )
}

export { Progress }
