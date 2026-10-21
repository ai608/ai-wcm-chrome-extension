import { afterEach, expect, it, vi } from 'vitest'
import { withReload } from '@/lib/lazy'

afterEach(() => sessionStorage.clear())

const missing = () => Promise.reject(new TypeError('Failed to fetch dynamically imported module'))

it('reloads once when a chunk is missing, then surfaces the error', async () => {
  const reload = vi.fn()
  void withReload(missing, reload)()
  await Promise.resolve()
  await Promise.resolve()
  expect(reload).toHaveBeenCalledTimes(1)
  await expect(withReload(missing, reload)()).rejects.toThrow('dynamically imported')
  expect(reload).toHaveBeenCalledTimes(1)
})

it('clears the flag after a successful load', async () => {
  sessionStorage.setItem('wcm:chunk-reload', '1')
  await expect(withReload(() => Promise.resolve('ok'), vi.fn())()).resolves.toBe('ok')
  expect(sessionStorage.getItem('wcm:chunk-reload')).toBeNull()
})
