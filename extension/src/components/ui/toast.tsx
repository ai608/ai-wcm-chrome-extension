import { Toast as ToastPrimitive } from '@base-ui/react/toast'
import { XIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

const toastManager = ToastPrimitive.createToastManager()

export function toast(title: string, description?: string) {
  toastManager.add({ title, description })
}

function ToastProvider({ children }: { children: React.ReactNode }) {
  const { toasts } = ToastPrimitive.useToastManager()
  return (
    <ToastPrimitive.Provider toastManager={toastManager} timeout={4000} limit={3}>
      {children}
      <ToastPrimitive.Portal>
        <ToastPrimitive.Viewport className="fixed bottom-2 left-2 right-2 z-50 flex w-auto flex-col gap-2 outline-none">
          {toasts.map((t) => (
            <ToastPrimitive.Root
              key={t.id}
              toast={t}
              className="flex items-start gap-2 rounded-lg border border-border bg-card px-3 py-2 text-card-foreground shadow-md"
            >
              <ToastPrimitive.Content className="flex-1">
                {t.title ? (
                  <ToastPrimitive.Title className="text-xs font-medium">
                    {t.title}
                  </ToastPrimitive.Title>
                ) : null}
                {t.description ? (
                  <ToastPrimitive.Description className="text-xs text-muted-foreground">
                    {t.description}
                  </ToastPrimitive.Description>
                ) : null}
              </ToastPrimitive.Content>
              <ToastPrimitive.Close
                aria-label="Dismiss"
                className={cn(
                  'rounded p-0.5 text-muted-foreground outline-none hover:text-foreground',
                  'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
                )}
              >
                <XIcon className="size-3.5" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          ))}
        </ToastPrimitive.Viewport>
      </ToastPrimitive.Portal>
    </ToastPrimitive.Provider>
  )
}

export { ToastProvider }
