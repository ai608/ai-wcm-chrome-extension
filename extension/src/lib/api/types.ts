export type FieldValue = string | number | string[] | null

export interface User {
  id: string
  email: string
  fullName: string
  role: 'owner' | 'admin' | 'user'
  hasExtensionAccess: boolean
}

export interface Config {
  ghlLocationId: string
  bookingWidgetUrl: string
  scriptVersion: number
}

export type BlockInput =
  | 'text'
  | 'textarea'
  | 'number'
  | 'currency'
  | 'select'
  | 'radio'
  | 'checkbox_group'

export interface BlockOption {
  value: string
  label: string
}

export type Block =
  | { type: 'say'; id: string; text: string; tone?: 'default' | 'highlight' }
  | { type: 'tip'; id: string; text: string }
  | { type: 'response'; id: string; label: string; text: string }
  | {
      type: 'question'
      id: string
      fieldKey: string
      label: string
      help?: string
      input: BlockInput
      options?: BlockOption[]
      requiredForBooking: boolean
    }
  | { type: 'recap'; id: string; rows: RecapRow[]; sayItBack: string }
  | { type: 'outcome'; id: string; outcomes: Outcome[] }
  | { type: 'booking'; id: string }
  | { type: 'faq'; id: string; items: { q: string; a: string }[] }
  | { type: 'do_not_book'; id: string; items: string[] }

export type RecapRow =
  | { label: string; source: 'field'; fieldKey: string }
  | { label: string; source: 'contact'; key: 'company_name' | 'postal_code' | 'city' }
  | {
      label: string
      source: 'computed'
      key: string
      formula: { op: 'multiply'; fields: [string, string] }
    }

export interface Outcome {
  id: string
  label: string
  books: boolean
}

export type Question = Extract<Block, { type: 'question' }>

export interface Section {
  id: string
  title: string
  defaultOpen: boolean
  blocks: Block[]
}

export interface FlowOption {
  id: string
  /** what the prospect answers */
  label: string
  /** what the rep replies */
  say: string
  next?: FlowNode
}

export interface FlowNode {
  /** the question the rep asks next (omitted when the response text already asks it) */
  ask?: string
  options: FlowOption[]
}

export interface ScriptDefinition {
  version: number
  sections: Section[]
  /** response block id -> conversation flow revealed once that response is ticked */
  flows?: Record<string, FlowNode>
}

export interface Contact {
  id: string
  firstName: string
  lastName: string
  companyName: string
  email: string
  phone: string
  city: string
  state: string
  postalCode: string
  website: string
  tags: string[]
}

export interface Enrichment {
  status: 'enriched' | 'not_enriched' | 'enriching'
  services: string[]
  googleRating: number | null
  googleReviewCount: number | null
  score: number | null
  updatedAt: string | null
}

export interface ContactContext {
  contact: Contact
  fieldValues: Record<string, FieldValue>
  enrichment: Enrichment
}

export interface PersonalizedScript {
  status: 'ready' | 'generating' | 'failed' | 'none'
  scriptVersion: number
  generatedAt: string | null
  slots: Record<string, string>
  error: string | null
}

export interface PatchFieldsResult {
  fieldValues: Record<string, FieldValue>
  updatedAt: string
}

export interface SaveOutcomeResult {
  noteId: string
  tag: string
}

export interface Activity {
  id: string
  kind: 'note' | 'call' | 'email' | 'sms' | 'task'
  source: string
  createdAt: string
  body: string
}

export interface Opportunity {
  id: string
  name: string
  monetaryValue: number
  status: 'open' | 'won' | 'lost' | 'abandoned'
  pipelineName: string | null
  stageName: string | null
}

export interface ContactHistory {
  brief: { text: string; generatedAt: string } | null
  activities: Activity[]
  opportunities: Opportunity[]
  lastContactedAt: string | null
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  expiresAt: string
}
