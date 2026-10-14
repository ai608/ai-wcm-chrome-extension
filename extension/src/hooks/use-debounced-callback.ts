import { useCallback, useEffect, useRef } from 'react'

export function useDebouncedCallback<A extends unknown[]>(fn: (...args: A) => void, delay: number) {
  const fnRef = useRef(fn)
  fnRef.current = fn
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  return useCallback(
    (...args: A) => {
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => fnRef.current(...args), delay)
    },
    [delay],
  )
}
