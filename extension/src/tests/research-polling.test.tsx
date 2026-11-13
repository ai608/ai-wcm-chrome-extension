import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/messaging', () => ({ call: vi.fn() }))

describe('usePollWindow', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('polls every 2s while busy, every 10s after 3 min (never gives up), resets when idle', async () => {
    const { usePollWindow, POLL_MS, SLOW_POLL_MS } = await import('@/hooks/research-queries')
    const { result, rerender } = renderHook(({ busy }) => usePollWindow(busy), {
      initialProps: { busy: false },
    })
    expect(result.current).toEqual([false, false])

    rerender({ busy: true })
    expect(result.current).toEqual([POLL_MS, false])

    act(() => {
      vi.advanceTimersByTime(3 * 60_000 + 10)
    })
    expect(result.current).toEqual([SLOW_POLL_MS, true])

    rerender({ busy: false })
    expect(result.current).toEqual([false, false])

    rerender({ busy: true })
    expect(result.current).toEqual([POLL_MS, false])
  })
})
