import * as z from 'zod/mini'
import { request } from '@/lib/api/client'
import { ApiError } from '@/lib/api/errors'
import type { Audit, ContactResearch, Report, SendReportResult } from '@/lib/api/research-types'
import { auditSchema, reportSchema } from '@/lib/api/schemas'

const camel = (k: string) => k.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())

// Wire is snake_case; section keys inside `section_state` are values-as-keys and stay as-is.
function camelize(v: unknown, keepKeys = false): unknown {
  if (Array.isArray(v)) return v.map((x) => camelize(x, keepKeys))
  if (v && typeof v === 'object') {
    return Object.fromEntries(
      Object.entries(v).map(([k, x]) => [
        keepKeys ? k : camel(k),
        camelize(x, k === 'section_state' || k === 'sectionState'),
      ]),
    )
  }
  return v
}

function parseAudit(data: unknown): Audit {
  const c = camelize(data)
  try {
    z.parse(auditSchema, c)
  } catch {
    throw new ApiError(200, 'invalid_response', 'Unexpected response from server')
  }
  return c as Audit
}

const base = (id: string) => `/research/audits/${id}`

export async function startAudit(url: string, force?: boolean): Promise<Audit> {
  return parseAudit(await request<unknown>('POST', '/research/audits', { body: { url, force } }))
}

export async function getAudit(auditId: string): Promise<Audit> {
  return parseAudit(await request<unknown>('GET', base(auditId), {}))
}

export async function getLatestAudit(domain: string): Promise<Audit | null> {
  try {
    return parseAudit(
      await request<unknown>(
        'GET',
        `/research/audits/latest?domain=${encodeURIComponent(domain)}`,
        {},
      ),
    )
  } catch (err) {
    if (err instanceof ApiError && err.code === 'audit_not_found') return null
    throw err
  }
}

export async function runDomainOverview(auditId: string): Promise<Audit> {
  return parseAudit(await request<unknown>('POST', `${base(auditId)}/domain-overview`, {}))
}

export async function runLocalCompetitors(
  auditId: string,
  query?: string,
  location?: string,
): Promise<Audit> {
  return parseAudit(
    await request<unknown>('POST', `${base(auditId)}/local-competitors`, {
      body: { query, location },
    }),
  )
}

export async function runAiVisibility(auditId: string, prompts: string[]): Promise<Audit> {
  return parseAudit(
    await request<unknown>('POST', `${base(auditId)}/ai-visibility`, { body: { prompts } }),
  )
}

export async function getReport(auditId: string): Promise<Report> {
  const c = camelize(await request<unknown>('GET', `${base(auditId)}/report`, {}))
  try {
    z.parse(reportSchema, c)
  } catch {
    throw new ApiError(200, 'invalid_response', 'Unexpected response from server')
  }
  return c as Report
}

export async function sendReport(
  auditId: string,
  email: string,
  note?: string,
): Promise<SendReportResult> {
  return camelize(
    await request<unknown>('POST', `${base(auditId)}/send`, { body: { email, note } }),
  ) as SendReportResult
}

function mapContactResearch(data: unknown): ContactResearch {
  const d = data as { audit: unknown | null; reason?: 'no_website' }
  return { audit: d.audit ? parseAudit(d.audit) : null, reason: d.reason }
}

export async function getContactResearch(contactId: string): Promise<ContactResearch> {
  return mapContactResearch(await request<unknown>('GET', `/contacts/${contactId}/research`, {}))
}

export async function startContactResearch(
  contactId: string,
  force?: boolean,
): Promise<ContactResearch> {
  return mapContactResearch(
    await request<unknown>('POST', `/contacts/${contactId}/research`, { body: { force } }),
  )
}
