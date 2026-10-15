import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

afterEach(cleanup)

it('clears cached account data when auth changes outside this panel', async () => {
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  fakeBrowser.reset()
  const { queryClient } = await import('@/app/providers')
  const { useAuth } = await import('@/hooks/use-auth')
  const { authUserItem } = await import('@/lib/storage')
  await authUserItem.setValue({
    id: 'user-1', email: 'a@example.com', fullName: 'A', role: 'user', hasExtensionAccess: true,
  })
  function Probe() {
    useAuth()
    return null
  }
  render(<Probe />)
  queryClient.setQueryData(['config'], { ghlLocationId: 'old-account' })

  await act(async () => { await authUserItem.setValue(null) })
  expect(queryClient.getQueryData(['config'])).toBeUndefined()
  queryClient.clear()
})
