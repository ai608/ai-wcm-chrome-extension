import { defineExtensionMessaging } from '@webext-core/messaging'
import { ApiError } from '@/lib/api/errors'
import type {
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

export interface ProtocolMap {
  login(data: { email: string; password: string; totpCode?: string }): User
  logout(): void
  getConfig(): Config
  getScriptDefinition(): ScriptDefinition
  getContactContext(data: { contactId: string }): ContactContext
  getPersonalizedScript(data: { contactId: string }): PersonalizedScript
  regenerateScript(data: { contactId: string }): PersonalizedScript
  patchFields(data: { contactId: string; fields: Record<string, FieldValue> }): PatchFieldsResult
  saveOutcome(data: {
    contactId: string
    outcomeId: string
    note: string
    booked: boolean
  }): SaveOutcomeResult
  enrichContact(data: { contactId: string }): { status: 'enriching' }
  getHistory(data: { contactId: string }): ContactHistory
}

export const { sendMessage, onMessage } = defineExtensionMessaging<ProtocolMap>()

export async function call<K extends keyof ProtocolMap>(
  type: K,
  ...args: Parameters<ProtocolMap[K]>
): Promise<ReturnType<ProtocolMap[K]>> {
  try {
    const data = args[0] as Parameters<ProtocolMap[K]>[0]
    if (data === undefined) {
      return (await (sendMessage as (...a: unknown[]) => unknown)(type)) as ReturnType<
        ProtocolMap[K]
      >
    }
    return (await (sendMessage as (...a: unknown[]) => unknown)(type, data)) as ReturnType<
      ProtocolMap[K]
    >
  } catch (err) {
    const restored = ApiError.fromJSON(err)
    if (restored) throw restored
    throw err
  }
}
