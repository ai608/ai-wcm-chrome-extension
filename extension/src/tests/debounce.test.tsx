import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDebouncedCallback } from '@/hooks/use-debounced-callback'

describe('useDebouncedCallback', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('calls once after the delay with the latest args', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 800))
    act(() => {
      result.current('a')
      result.current('b')
    })
    expect(fn).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(800))
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('b')
  })

  it('resets the delay on each call', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current())
    act(() => vi.advanceTimersByTime(200))
    act(() => result.current())
    act(() => vi.advanceTimersByTime(200))
    expect(fn).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(100))
    expect(fn).toHaveBeenCalledTimes(1)
  })
})
