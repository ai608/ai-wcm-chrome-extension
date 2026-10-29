import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import type { User } from '@/lib/api/types'

vi.mock('@/hooks/use-auth', () => ({ logout: () => Promise.resolve() }))

const user: User = {
  id: 'u1',
  email: 'sam@example.com',
  fullName: 'Sam Rivera',
  role: 'user',
  hasExtensionAccess: true,
}

beforeEach(() => {
  vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  fakeBrowser.reset()
  vi.spyOn(fakeBrowser.runtime, 'getManifest').mockReturnValue({
    version: '0.1.0',
  } as ReturnType<typeof fakeBrowser.runtime.getManifest>)
  window.matchMedia = ((q: string) => ({
    matches: true,
    media: q,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
})
afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
})

it('has no theme button in the panel header', async () => {
  const { PanelHeader } = await import('@/components/panel/PanelHeader')
  render(<PanelHeader />)
  expect(screen.queryByTitle(/mode/i)).toBeNull()
})

it('switches between light, dark and system from Settings', async () => {
  const { SettingsScreen } = await import('@/components/panel/SettingsScreen')
  render(<SettingsScreen user={user} />)
  const root = document.documentElement
  await act(async () => {})
  // system follows the (mocked) dark OS setting
  expect(screen.getByRole('button', { name: 'System' }).getAttribute('aria-pressed')).toBe('true')
  expect(root.classList.contains('dark')).toBe(true)
  for (const [name, dark] of [
    ['Light', false],
    ['Dark', true],
    ['Light', false],
    ['System', true],
  ] as const) {
    fireEvent.click(screen.getByRole('button', { name }))
    await act(async () => {})
    expect(root.classList.contains('dark')).toBe(dark)
    expect(screen.getByRole('button', { name }).getAttribute('aria-pressed')).toBe('true')
  }
})
