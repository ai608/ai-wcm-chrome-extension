import { type ComponentType, lazy } from 'react'

const FLAG = 'wcm:chunk-reload'

/**
 * A panel opened before an extension rebuild asks for chunk hashes that no longer exist.
 * Reload once to pick up the new build instead of crashing; the session flag stops a
 * reload loop if the chunk is genuinely missing.
 */
export function withReload<T>(
  load: () => Promise<T>,
  reload: () => void = () => window.location.reload(),
): () => Promise<T> {
  return () =>
    load().then(
      (mod) => {
        try {
          sessionStorage.removeItem(FLAG)
        } catch {}
        return mod
      },
      (err: unknown) => {
        let first = false
        try {
          first = !sessionStorage.getItem(FLAG)
          if (first) sessionStorage.setItem(FLAG, '1')
        } catch {}
        if (!first) throw err
        reload()
        return new Promise<T>(() => {}) // page is reloading
      },
    )
}

export function lazyWithReload<P extends object>(
  load: () => Promise<{ default: ComponentType<P> }>,
) {
  return lazy(withReload(load))
}
