import * as z from 'zod/mini'
import { request } from '@/lib/api/client'
import { ApiError } from '@/lib/api/errors'
import { configSchema, patchFieldsResponseSchema, scriptDefinitionSchema } from '@/lib/api/schemas'
import type {
  Activity,
  AuthTokens,
  Config,
  Contact,
  ContactContext,
  ContactHistory,
  Enrichment,
  FieldValue,
  Opportunity,
  PatchFieldsResult,
  PersonalizedScript,
  SaveOutcomeResult,
  ScriptDefinition,
  User,
} from '@/lib/api/types'

function invalidResponse(): ApiError {
  return new ApiError(200, 'invalid_response', 'Unexpected response from server')
}

function parse<T>(schema: z.ZodMiniType<T, unknown>, data: unknown): T {
  try {
    return z.parse(schema, data)
  } catch {
    throw invalidResponse()
  }
}

interface WireUser {
  id: string
  email: string
  full_name: string
  role: 'owner' | 'admin' | 'user'
  has_extension_access: boolean
}

interface WireAuth {
  access_token: string
  refresh_token: string
  expires_at: string
  user: WireUser
}

function mapUser(u: WireUser): User {
  return {
    id: u.id,
    email: u.email,
    fullName: u.full_name,
    role: u.role,
    hasExtensionAccess: u.has_extension_access,
  }
}

function mapAuth(data: WireAuth): { tokens: AuthTokens; user: User } {
  return {
    tokens: {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresAt: data.expires_at,
    },
    user: mapUser(data.user),
  }
}

export async function exchangeWeb(
  code: string,
  state: string,
  verifier: string,
  extensionId: string,
): Promise<{ tokens: AuthTokens; user: User }> {
  const data = await request<WireAuth>('POST', '/auth/web-exchange', {
    auth: false,
    body: { code, state, verifier, extension_id: extensionId },
  })
  return mapAuth(data)
}

export async function login(
  email: string,
  password: string,
  totpCode?: string,
): Promise<{ tokens: AuthTokens; user: User }> {
  const data = await request<WireAuth>('POST', '/auth/login', {
    auth: false,
    body: totpCode ? { email, password, totp_code: totpCode } : { email, password },
  })
  return mapAuth(data)
}

export async function logout(): Promise<void> {
  await request<void>('POST', '/auth/logout', {})
}

export async function getMe(): Promise<User> {
  return mapUser(await request<WireUser>('GET', '/me', {}))
}

export async function getConfig(): Promise<Config> {
  const data = await request<unknown>('GET', '/config', {})
  const parsed = parse(configSchema, data)
  return {
    ghlLocationId: parsed.ghl_location_id,
    bookingWidgetUrl: parsed.booking_widget_url,
    scriptVersion: parsed.script_version,
  }
}

export async function getScriptDefinition(): Promise<ScriptDefinition> {
  const data = await request<unknown>('GET', '/script', {})
  return parse(scriptDefinitionSchema, data) as ScriptDefinition
}

interface WireContact {
  id: string
  first_name: string
  last_name: string
  company_name: string
  email: string
  phone: string
  city: string
  state: string
  postal_code: string
  website: string
  tags: string[]
}

interface WireEnrichment {
  status: 'enriched' | 'not_enriched' | 'enriching'
  services: string[]
  google_rating: number | null
  google_review_count: number | null
  score: number | null
  updated_at: string | null
}

interface WireContext {
  contact: WireContact
  field_values: Record<string, FieldValue>
  enrichment: WireEnrichment
}

function mapContact(c: WireContact): Contact {
  return {
    id: c.id,
    firstName: c.first_name,
    lastName: c.last_name,
    companyName: c.company_name,
    email: c.email,
    phone: c.phone,
    city: c.city,
    state: c.state,
    postalCode: c.postal_code,
    website: c.website,
    tags: c.tags,
  }
}

function mapEnrichment(e: WireEnrichment): Enrichment {
  return {
    status: e.status,
    services: e.services,
    googleRating: e.google_rating,
    googleReviewCount: e.google_review_count,
    score: e.score,
    updatedAt: e.updated_at,
  }
}

export async function getContactContext(contactId: string): Promise<ContactContext> {
  const data = await request<WireContext>('GET', `/contacts/${contactId}/context`, {})
  return {
    contact: mapContact(data.contact),
    fieldValues: data.field_values,
    enrichment: mapEnrichment(data.enrichment),
  }
}

interface WireScript {
  status: 'ready' | 'generating' | 'failed' | 'none'
  script_version: number
  generated_at: string | null
  slots: Record<string, string>
  error: string | null
}

function mapScript(s: WireScript): PersonalizedScript {
  return {
    status: s.status,
    scriptVersion: s.script_version,
    generatedAt: s.generated_at,
    slots: s.slots,
    error: s.error,
  }
}

export async function getPersonalizedScript(contactId: string): Promise<PersonalizedScript> {
  return mapScript(await request<WireScript>('GET', `/contacts/${contactId}/script`, {}))
}

export async function regenerateScript(contactId: string): Promise<PersonalizedScript> {
  return mapScript(
    await request<WireScript>('POST', `/contacts/${contactId}/script/regenerate`, {}),
  )
}

export async function patchFields(
  contactId: string,
  fields: Record<string, FieldValue>,
): Promise<PatchFieldsResult> {
  const data = await request<unknown>('PATCH', `/contacts/${contactId}/fields`, {
    body: { fields },
  })
  const parsed = parse(patchFieldsResponseSchema, data)
  return { fieldValues: parsed.field_values, updatedAt: parsed.updated_at }
}

export async function saveOutcome(
  contactId: string,
  outcomeId: string,
  note: string,
  booked: boolean,
): Promise<SaveOutcomeResult> {
  const data = await request<{ note_id: string; tag: string }>(
    'POST',
    `/contacts/${contactId}/outcome`,
    { body: { outcome_id: outcomeId, note, booked } },
  )
  return { noteId: data.note_id, tag: data.tag }
}

export async function enrichContact(contactId: string): Promise<{ status: 'enriching' }> {
  return request<{ status: 'enriching' }>('POST', `/contacts/${contactId}/enrich`, {})
}

interface WireActivity {
  id: string
  kind: 'note' | 'call' | 'email' | 'sms' | 'task'
  source: string
  created_at: string
  body: string
}

interface WireOpportunity {
  id: string
  name: string
  monetary_value: number
  status: 'open' | 'won' | 'lost' | 'abandoned'
  pipeline_name: string | null
  stage_name: string | null
}

interface WireHistory {
  brief: { text: string; generated_at: string } | null
  activities: WireActivity[]
  opportunities: WireOpportunity[]
  last_contacted_at: string | null
}

export async function getHistory(contactId: string): Promise<ContactHistory> {
  const data = await request<WireHistory>('GET', `/contacts/${contactId}/history`, {})
  const activities: Activity[] = data.activities.map((a) => ({
    id: a.id,
    kind: a.kind,
    source: a.source,
    createdAt: a.created_at,
    body: a.body,
  }))
  const opportunities: Opportunity[] = data.opportunities.map((o) => ({
    id: o.id,
    name: o.name,
    monetaryValue: o.monetary_value,
    status: o.status,
    pipelineName: o.pipeline_name,
    stageName: o.stage_name,
  }))
  return {
    brief: data.brief ? { text: data.brief.text, generatedAt: data.brief.generated_at } : null,
    activities,
    opportunities,
    lastContactedAt: data.last_contacted_at,
  }
}
export * from '@/lib/api/o4-research'
