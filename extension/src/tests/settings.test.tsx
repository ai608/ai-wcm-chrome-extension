import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import type { User } from '@/lib/api/types'
import { usePanelStore } from '@/stores/panel-store'

const logoutMock = vi.fn()

vi.mock('@/hooks/use-auth', () => ({ logout: () => logoutMock() }))

const user: User = {
  id: 'u1',
  email: 'sam@example.com',
  fullName: 'Sam Rivera',
  role: 'user',
  hasExtensionAccess: true,
}

describe('SettingsScreen', () => {
  beforeEach(() => {
    fakeBrowser.reset()
    vi.spyOn(fakeBrowser.runtime, 'getManifest').mockReturnValue({
      version: '0.1.0',
    } as ReturnType<typeof fakeBrowser.runtime.getManifest>)
    vi.stubGlobal('browser', fakeBrowser)
    vi.stubGlobal('chrome', fakeBrowser)
    vi.stubEnv('WXT_GHL_HOST', 'app.example.com')
    vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
    vi.stubEnv('WXT_API_MOCK', 'true')
    usePanelStore.setState({ view: 'settings' })
    logoutMock.mockReset()
    logoutMock.mockResolvedValue(undefined)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('shows the account and returns to the assistant', async () => {
    const { SettingsScreen } = await import('@/components/panel/SettingsScreen')
    render(<SettingsScreen user={user} />)
    expect(screen.getByText('Sam Rivera')).toBeDefined()
    expect(screen.queryByRole('radio')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Back to assistant' }))
    expect(usePanelStore.getState().view).toBe('main')
  })

  it('keeps the confirmation open when sign-out fails', async () => {
    const { SettingsScreen } = await import('@/components/panel/SettingsScreen')
    logoutMock.mockRejectedValueOnce(new Error('Could not reach the extension'))
    render(<SettingsScreen user={user} />)

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Could not reach the extension',
    )
    expect(usePanelStore.getState().view).toBe('settings')
  })
})
