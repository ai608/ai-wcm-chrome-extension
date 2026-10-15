import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeBrowser } from 'wxt/testing/fake-browser'
import { usePanelStore } from '@/stores/panel-store'

async function renderApp() {
  const { default: App } = await import('@/app/App')
  return render(<App />)
}

const authState: { user: unknown; isLoading: boolean } = { user: undefined, isLoading: true }
let activeTab: unknown
let config: unknown

vi.mock('@/hooks/use-auth', () => ({
  useAuth: () => authState,
  login: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('@/hooks/use-active-tab', () => ({
  useActiveTab: () => activeTab,
}))

vi.mock('@/hooks/queries', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/hooks/queries')>()
  return {
    ...mod,
    useConfigQuery: () => ({ data: config, isPending: config === undefined, isError: false }),
  }
})

vi.mock('@/hooks/use-script-state', () => ({
  useScriptState: () => ({
    definition: undefined,
    definitionPending: false,
    definitionError: null,
    context: {
      contact: {
        id: 'c1',
        firstName: 'M',
        lastName: 'R',
        companyName: 'Glow',
        email: '',
        phone: '',
        city: 'Austin',
        state: 'TX',
        postalCode: '',
        website: '',
        tags: [],
      },
      fieldValues: {},
      enrichment: {
        status: 'enriched',
        services: [],
        googleRating: null,
        googleReviewCount: null,
        score: null,
        updatedAt: null,
      },
    },
    contextPending: false,
    contextError: null,
    script: undefined,
    scriptPending: false,
    timedOut: false,
    enrichPending: false,
    regeneratePending: false,
    startEnrich: vi.fn(),
    startRegenerate: vi.fn(),
  }),
}))

vi.mock('@/components/script/ScriptTab', () => ({
  ScriptTab: () => <p>Script body</p>,
}))

const USER = {
  id: 'u1',
  email: 'sdr@example.com',
  fullName: 'Sam Rivera',
  role: 'user',
  hasExtensionAccess: true,
}

describe('App view switch', () => {
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
    usePanelStore.setState({ view: 'main' })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('shows login when signed out', async () => {
    authState.user = null
    authState.isLoading = false
    await renderApp()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDefined()
  })

  it('shows no-access without the grant', async () => {
    authState.user = { ...USER, hasExtensionAccess: false }
    authState.isLoading = false
    await renderApp()
    expect(screen.getByText('No extension access')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(screen.getByText('Connection')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Back to assistant' }))
    expect(screen.getByText('No extension access')).toBeDefined()
  })

  it('shows no-contact without a contact page', async () => {
    authState.user = USER
    authState.isLoading = false
    activeTab = { tabId: 1, url: 'https://app.example.com/', kind: 'ghl_other' }
    config = { ghlLocationId: 'L1', bookingWidgetUrl: 'about:blank', scriptVersion: 3 }
    await renderApp()
    expect(screen.getByText('Open a contact in GoHighLevel')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeDefined()
  })

  it('blocks the wrong ghl account', async () => {
    authState.user = USER
    authState.isLoading = false
    activeTab = { tabId: 1, url: 'x', kind: 'ghl_contact', locationId: 'OTHER', contactId: 'c1' }
    config = { ghlLocationId: 'L1', bookingWidgetUrl: 'about:blank', scriptVersion: 3 }
    await renderApp()
    expect(screen.getByText('Wrong GHL account')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeDefined()
  })

  it('renders call mode on the sales account', async () => {
    authState.user = USER
    authState.isLoading = false
    activeTab = { tabId: 1, url: 'x', kind: 'ghl_contact', locationId: 'L1', contactId: 'c1' }
    config = { ghlLocationId: 'L1', bookingWidgetUrl: 'about:blank', scriptVersion: 3 }
    await renderApp()
    expect(screen.getByText('Script body')).toBeDefined()
    expect(screen.getAllByText('Call Mode').length).toBeGreaterThan(0)
  })

  it('shows the unsupported screen on chrome:// pages', async () => {
    authState.user = USER
    authState.isLoading = false
    activeTab = { tabId: 1, url: 'chrome://extensions', kind: 'unsupported' }
    await renderApp()
    expect(screen.getByText('Open a clinic website or a GHL contact')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeDefined()
  })
})
