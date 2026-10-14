import { Button } from '@/components/ui/button'

export function ResearchTab() {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      <p className="max-w-60 text-xs text-muted-foreground">
        Research is coming soon — Google Business Profile, website, and local competitors will
        appear here.
      </p>
      <Button variant="outline" disabled>
        Refresh research
      </Button>
    </div>
  )
}
