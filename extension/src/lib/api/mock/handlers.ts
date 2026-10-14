import { ApiError } from '@/lib/api/errors'
import {
  cloneState,
  initialStates,
  MOCK_LOCATION_ID,
  scriptDefinition,
  vitalEnrichedContext,
  vitalSlots,
} from '@/lib/api/mock/fixtures'
import { __resetResearchMock } from '@/lib/api/mock/research-handlers'
import type {
  AuthTokens,
  Config,
  ContactContext,
  ContactHistory,
  FieldValue,
  PatchFieldsResult,
  PersonalizedScript,
  SaveOutcomeResult,
  ScriptDefinition,
  User,
} from '@/lib/api/types'

interface ContactState {
  context: ContactContext
  script: PersonalizedScript
  history: ContactHistory
  scriptReadyAt: number | null
  enrichReadyAt: number | null
}

const states = new Map<string, ContactState>()
let currentUser: User = demoUser('sdr@wellnessclinicmarketing.com')

function demoUser(email: string): User {
  return {
    id: 'u_demo',
    email,
    fullName: 'Sam Rivera',
    role: 'user',
    hasExtensionAccess: !email.includes('noaccess'),
  }
}

function latency(): Promise<void> {
  return new Promise((r) => setTimeout(r, 300 + Math.random() * 300))
}

function notFound(): ApiError {
  return new ApiError(404, 'contact_not_found', 'Contact not found in GHL')
}

function stateFor(contactId: string): ContactState {
  const existing = states.get(contactId)
  if (existing) {
    if (existing.enrichReadyAt != null && Date.now() >= existing.enrichReadyAt) {
      existing.enrichReadyAt = null
      existing.context = vitalEnrichedContext()
      existing.script = {
        status: 'generating',
        scriptVersion: 3,
        generatedAt: null,
        slots: {},
        error: null,
      }
      existing.scriptReadyAt = Date.now() + 3000
    }
    if (existing.scriptReadyAt != null && Date.now() >= existing.scriptReadyAt) {
      existing.scriptReadyAt = null
      existing.script = {
        status: 'ready',
        scriptVersion: 3,
        generatedAt: new Date().toISOString(),
        slots: contactId === 'c_vital' ? vitalSlots : peakSlots(),
        error: null,
      }
    }
    return existing
  }
  if (!initialStates[contactId]) throw notFound()
  const fresh = cloneState(contactId) as unknown as ContactState
  if (contactId === 'c_peak') fresh.scriptReadyAt = Date.now() + 5000
  states.set(contactId, fresh)
  return fresh
}

function peakSlots(): Record<string, string> {
  return {
    opener:
      'Your Denver locations have 341 reviews at 4.9 — that kind of reputation usually means ads scale fast.',
    hook: 'Multi-location chiro groups typically see cost per booked exam drop by a third once intake is centralized.',
    qualifier: 'who handles marketing across the two locations today?',
    objection_hint: 'If they mention their agency contract, ask when it renews.',
    booking_push: 'I can hold a slot Thursday or Friday — which is calmer at the front desk?',
  }
}

function tokensFor(email: string): AuthTokens {
  void email
  return {
    accessToken: 'mock-access',
    refreshToken: 'mock-refresh',
    expiresAt: '2030-01-01T00:00:00Z',
  }
}

export async function login(
  email: string,
  password: string,
  totpCode?: string,
): Promise<{ tokens: AuthTokens; user: User }> {
  await latency()
  if (password === 'totp' && !totpCode) {
    throw new ApiError(401, 'totp_required', 'Two-factor code required')
  }
  if (password === 'totp') {
    if (totpCode !== '123456') throw new ApiError(401, 'invalid_totp', 'Invalid code')
    currentUser = demoUser(email)
    return { tokens: tokensFor(email), user: currentUser }
  }
  if (password !== 'demo') {
    throw new ApiError(401, 'invalid_credentials', 'Invalid email or password')
  }
  currentUser = demoUser(email)
  return { tokens: tokensFor(email), user: currentUser }
}

export async function logout(): Promise<void> {
  await latency()
}

export async function getMe(): Promise<User> {
  await latency()
  return currentUser
}

export async function getConfig(): Promise<Config> {
  await latency()
  return { ghlLocationId: MOCK_LOCATION_ID, bookingWidgetUrl: 'about:blank', scriptVersion: 3 }
}

export async function getScriptDefinition(): Promise<ScriptDefinition> {
  await latency()
  return structuredClone(scriptDefinition)
}

export async function getContactContext(contactId: string): Promise<ContactContext> {
  await latency()
  return structuredClone(stateFor(contactId).context)
}

export async function getPersonalizedScript(contactId: string): Promise<PersonalizedScript> {
  await latency()
  const s = stateFor(contactId)
  if (s.script.status === 'generating') return { ...s.script }
  return structuredClone(s.script)
}

export async function regenerateScript(contactId: string): Promise<PersonalizedScript> {
  await latency()
  const s = stateFor(contactId)
  s.script = { status: 'generating', scriptVersion: 3, generatedAt: null, slots: {}, error: null }
  s.scriptReadyAt = Date.now() + 3000
  return { ...s.script }
}

export async function patchFields(
  contactId: string,
  fields: Record<string, FieldValue>,
): Promise<PatchFieldsResult> {
  await latency()
  const s = stateFor(contactId)
  if (contactId === 'c_fail' && 'contact.annual_revenue' in fields) {
    throw new ApiError(422, 'validation_error', 'annual_revenue: enter a valid amount')
  }
  for (const [k, v] of Object.entries(fields)) s.context.fieldValues[k] = v
  return { fieldValues: { ...s.context.fieldValues }, updatedAt: new Date().toISOString() }
}

export async function saveOutcome(
  contactId: string,
  outcomeId: string,
  note: string,
  booked: boolean,
): Promise<SaveOutcomeResult> {
  await latency()
  const s = stateFor(contactId)
  const noteId = `n_${Date.now()}`
  s.history.activities.unshift({
    id: noteId,
    kind: 'note',
    source: currentUser.fullName,
    createdAt: new Date().toISOString(),
    body: `${note}${booked ? '\nAppointment booked: yes' : ''}`,
  })
  void outcomeId
  return { noteId, tag: outcomeId }
}

export async function enrichContact(contactId: string): Promise<{ status: 'enriching' }> {
  await latency()
  const s = stateFor(contactId)
  s.context.enrichment = { ...s.context.enrichment, status: 'enriching' }
  s.enrichReadyAt = Date.now() + 3000
  return { status: 'enriching' }
}

export async function getHistory(contactId: string): Promise<ContactHistory> {
  await latency()
  return structuredClone(stateFor(contactId).history)
}

export * from '@/lib/api/mock/research-handlers'

export function __resetMock() {
  __resetResearchMock()
  states.clear()
  currentUser = demoUser('sdr@wellnessclinicmarketing.com')
}
