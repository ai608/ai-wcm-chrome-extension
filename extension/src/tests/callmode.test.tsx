import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'

vi.mock('@/lib/messaging', async () => {
  const api = await import('@/lib/api/mock/handlers')
  return {
    call: async (key: string, data: Record<string, unknown> = {}) => {
      const map: Record<string, () => unknown> = {
        getScriptDefinition: () => api.getScriptDefinition(),
        getContactContext: () => api.getContactContext(data.contactId as string),
        getPersonalizedScript: () => api.getPersonalizedScript(data.contactId as string),
        getContactResearch: () => api.getContactResearch(data.contactId as string),
        getHistory: () => api.getHistory(data.contactId as string),
        regenerateScript: () => api.regenerateScript(data.contactId as string),
        enrichContact: () => api.enrichContact(data.contactId as string),
        patchFields: () => api.patchFields(data.contactId as string, data.fields as never),
      }
      return map[key]?.()
    },
  }
})

beforeEach(() => {
  vi.stubEnv('WXT_GHL_HOST', 'example.com')
  vi.stubEnv('WXT_API_BASE_URL', 'http://localhost:8000')
  vi.stubEnv('WXT_API_MOCK', 'true')
  vi.stubGlobal('browser', fakeBrowser)
  vi.stubGlobal('chrome', fakeBrowser)
  fakeBrowser.reset()
  window.matchMedia = (() => ({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
})
afterEach(cleanup)

it.each(['c_glow', 'c_vital', 'c_peak', 'c_fail'])('CallMode %s has no update loop', async (id) => {
  const { Providers } = await import('@/app/providers')
  const { CallMode } = await import('@/components/panel/CallMode')
  render(
    <Providers>
      <CallMode
        activeContact={{ tabId: 1, url: 'x', locationId: 'MOCK_LOCATION', contactId: id }}
        callerFirstName="Sam"
        bookingWidgetUrl="about:blank"
      />
    </Providers>,
  )
  await waitFor(() => expect(screen.getAllByText('Opener').length).toBeGreaterThan(0), {
    timeout: 3000,
  })
  await new Promise((r) => setTimeout(r, 1500))
  fireEvent.click(screen.getByText('History'))
  fireEvent.click(screen.getByText('Research'))
  fireEvent.click(screen.getByText('Script'))
  await waitFor(() => expect(screen.getAllByText('Opener').length).toBeGreaterThan(0))
  fireEvent.click(screen.getAllByText('Opener')[0] as Element)
  fireEvent.click(screen.getAllByText('Opener')[0] as Element)
  for (const el of document.querySelectorAll('input[type=text], input:not([type]), textarea')) {
    fireEvent.change(el, { target: { value: '12' } })
  }
  for (const cb of document.querySelectorAll('[role=checkbox]')) fireEvent.click(cb)
  fireEvent.click(screen.getByTitle(/mode/i))
  fireEvent.click(screen.getByTitle(/mode/i))
  await new Promise((r) => setTimeout(r, 1500))
  expect(screen.queryByText('Something went wrong')).toBeNull()
})
