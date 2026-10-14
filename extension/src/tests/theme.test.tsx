import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

beforeEach(() => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  fakeBrowser.reset()
  window.matchMedia = ((q: string) => ({
    matches: true,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
})
afterEach(cleanup)

it('toggles dark <-> light repeatedly', async () => {
  const { PanelHeader } = await import('@/components/panel/PanelHeader')
  render(<PanelHeader />)
  const root = document.documentElement
  await act(async () => {})
  expect(root.classList.contains('dark')).toBe(true)
  for (const expected of [false, true, false]) {
    fireEvent.click(screen.getByTitle(/mode/i))
    await act(async () => {})
    expect(root.classList.contains('dark')).toBe(expected)
  }
})
