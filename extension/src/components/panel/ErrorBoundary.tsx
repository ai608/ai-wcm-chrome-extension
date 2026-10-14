import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    // keep the failing component stack in the console so crashes are diagnosable
    console.error('[WCM panel crash]', error, info.componentStack)
  }

  override render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-4">
          <p className="text-sm font-medium">Something went wrong</p>
          <p className="max-w-full break-words text-center text-[12px] text-muted-foreground">
            {this.state.error.message.slice(0, 200)}
          </p>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Reload panel
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}
