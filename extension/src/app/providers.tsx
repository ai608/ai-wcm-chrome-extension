import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from '@/components/panel/ErrorBoundary'
import { ToastProvider } from '@/components/ui/toast'
import { ApiError } from '@/lib/api/errors'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: (count, err) =>
        count < 1 && !(err instanceof ApiError && err.status >= 400 && err.status < 500),
    },
  },
})

export { queryClient }

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ErrorBoundary>{children}</ErrorBoundary>
      </ToastProvider>
    </QueryClientProvider>
  )
}
