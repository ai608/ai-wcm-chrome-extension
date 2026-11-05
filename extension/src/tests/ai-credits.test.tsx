import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import type { AiUsage, User } from '@/lib/api/types'
import { usePanelStore } from '@/stores/panel-store'

vi.mock('@/hooks/use-auth', () => ({ logout: async () => {} }))

const calls: { key: string; data: unknown }[] = []
let reply: () => Promise<AiUsage>
vi.mock('@/lib/messaging', () => ({
  call: async (key: string, data: unknown) => {
    calls.push({ key, data })
    return reply()
  },
}))

const usage = (over: Partial<AiUsage> = {}): AiUsage => ({
  configured: true,
  account: { creditsUsd: 85, usedUsd: 74.7198, remainingUsd: 10.2802 },
  key: { usedUsd: 28.5231, todayUsd: 4.9007, weekUsd: 11.2247, monthUsd: 11.2247, limitUsd: 250 },
  errors: {},
  tracked: {
    totalUsd: 0.5564,
    todayUsd: 0.5564,
    weekUsd: 0.5564,
    monthUsd: 0.5564,
    auditsUsd: 0.1226,
    aiVisibilityUsd: 0.4338,
    users: 2,
  },
  fetchedAt: '2026-11-04T14:00:00Z',
  ...over,
})

const person = (role: User['role']): User => ({
  id: 'u1',
  email: 'boss@example.com',
  fullName: 'Boss',
  role,
  hasExtensionAccess: true,
})

async function show(role: User['role']) {
  const { Providers } = await import('@/app/providers')
  const { SettingsScreen } = await import('@/components/panel/SettingsScreen')
  return render(
    <Providers>
      <SettingsScreen user={person(role)} />
    </Providers>,
  )
}

beforeEach(async () => {
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
  calls.length = 0
  reply = async () => usage()
  const { queryClient } = await import('@/app/providers')
  queryClient.clear()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('Settings: AI credits of all users', () => {
  it.each(['owner', 'admin'] as const)(
    '%s sees the balance and the all-users totals',
    async (role) => {
      await show(role)
      expect(await screen.findByText('$10.28')).toBeTruthy()
      expect(screen.getByText(/\$74\.72 used of \$85\.00 bought/)).toBeTruthy()
      expect(screen.getByText(/also counts other keys and apps/)).toBeTruthy()
      const row = (label: string) => screen.getByText(label).nextElementSibling?.textContent
      expect(row('All users, all time')).toBe('$28.52')
      expect(row('Today')).toBe('$4.90')
      expect(row('Last 7 days')).toBe('$11.22')
      expect(row('Last 30 days')).toBe('$11.22')
      expect(screen.getByText(/audits \$0\.12 · AI visibility \$0\.43 · 2 users/)).toBeTruthy()
      expect(calls).toEqual([{ key: 'getAiUsage', data: {} }])
    },
  )

  it('a plain user never sees the card and the server is never asked', async () => {
    await show('user')
    expect(screen.getByText('Account')).toBeTruthy()
    expect(screen.queryByText('AI credits')).toBeNull()
    expect(calls).toEqual([])
  })

  it('warns when under a fifth of the bought credits is left, and not before', async () => {
    await show('owner')
    expect(await screen.findByText('Running low')).toBeTruthy()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('88')
    cleanup()
    reply = async () => usage({ account: { creditsUsd: 85, usedUsd: 25, remainingUsd: 60 } })
    const { queryClient } = await import('@/app/providers')
    queryClient.clear()
    await show('owner')
    expect(await screen.findByText('$60.00')).toBeTruthy()
    expect(screen.queryByText('Running low')).toBeNull()
  })

  it('says which part could not be read and still shows the other', async () => {
    reply = async () => usage({ account: null, errors: { account: 'HTTP 403' } })
    await show('admin')
    expect(await screen.findByText(/Could not read the account balance \(HTTP 403\)/)).toBeTruthy()
    expect(screen.getByText('$28.52')).toBeTruthy()
  })

  it('says so when OpenRouter is not set up, and when the request fails', async () => {
    reply = async () => usage({ configured: false, account: null, key: null })
    await show('owner')
    expect(await screen.findByText(/OpenRouter is not set up/)).toBeTruthy()
    cleanup()
    reply = async () => {
      throw new Error('Only an owner or admin can see AI usage')
    }
    const { queryClient } = await import('@/app/providers')
    queryClient.clear()
    await show('owner')
    expect(await screen.findByText(/Only an owner or admin can see AI usage/)).toBeTruthy()
  })

  it('Refresh asks the server to skip its one-minute cache', async () => {
    await show('owner')
    await screen.findByText('$10.28')
    reply = async () => usage({ account: { creditsUsd: 85, usedUsd: 70, remainingUsd: 15 } })
    fireEvent.click(screen.getByRole('button', { name: 'Refresh AI credits' }))
    await waitFor(() => expect(screen.getByText('$15.00')).toBeTruthy())
    expect(calls.at(-1)).toEqual({ key: 'getAiUsage', data: { refresh: true } })
  })
})
