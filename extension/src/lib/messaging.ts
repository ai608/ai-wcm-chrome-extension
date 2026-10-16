import { defineExtensionMessaging } from '@webext-core/messaging'
import { ApiError } from '@/lib/api/errors'
import type { Audit, ContactResearch, Report, SendReportResult } from '@/lib/api/research-types'
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
  connectWeb(): void
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
  startAudit(data: { url: string; force?: boolean }): Audit
  getAudit(data: { auditId: string }): Audit
  getLatestAudit(data: { domain: string }): Audit | null
  runDomainOverview(data: { auditId: string }): Audit
  runLocalCompetitors(data: { auditId: string; query?: string; location?: string }): Audit
  runAiVisibility(data: { auditId: string; prompts: string[] }): Audit
  getReport(data: { auditId: string }): Report
  sendReport(data: { auditId: string; email: string; note?: string }): SendReportResult
  getContactResearch(data: { contactId: string }): ContactResearch
  startContactResearch(data: { contactId: string; force?: boolean }): ContactResearch
  openReport(data: { auditId: string }): void
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
