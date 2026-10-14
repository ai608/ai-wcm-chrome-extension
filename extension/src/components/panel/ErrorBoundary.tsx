import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  override render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-4">
          <p className="text-sm font-medium">Something went wrong</p>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload panel
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}
