import type { Contact, FieldValue } from '@/lib/api/types'
import { formatCurrency } from '@/lib/time'

export type Segment =
  | { kind: 'text'; value: string }
  | { kind: 'value'; value: string }
  | { kind: 'missing'; label: string }
  | { kind: 'pending' }

export interface TemplateCtx {
  contact: Contact
  fields: Record<string, FieldValue>
  computed: Record<string, number | null>
  slots: Record<string, string>
  slotsPending: boolean
  omitAi: boolean
  callerFirstName: string
}

export function humanize(key: string): string {
  return key
    .replace(/^contact\./, '')
    .replace(/^computed\./, '')
    .replace(/^ai\./, '')
    .replace(/_/g, ' ')
}

const CONTACT_PROPS: Record<string, (c: Contact) => string> = {
  first_name: (c) => c.firstName,
  last_name: (c) => c.lastName,
  company_name: (c) => c.companyName,
  email: (c) => c.email,
  phone: (c) => c.phone,
  city: (c) => c.city,
  state: (c) => c.state,
  postal_code: (c) => c.postalCode,
  website: (c) => c.website,
}

function fieldText(value: FieldValue | undefined): string | null {
  if (value == null) return null
  if (Array.isArray(value)) return value.length > 0 ? value.join(', ') : null
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : null
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

export function renderTemplate(text: string, ctx: TemplateCtx): Segment[] {
  const segments: Segment[] = []
  const push = (s: Segment) => {
    const last = segments[segments.length - 1]
    if (last && last.kind === 'text' && s.kind === 'text') last.value += s.value
    else segments.push(s)
  }
  const re = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    if (match.index > cursor) push({ kind: 'text', value: text.slice(cursor, match.index) })
    cursor = match.index + match[0].length
    const key = match[1] ?? ''
    const [ns, ...rest] = key.split('.')
    const name = rest.join('.')
    if (ns === 'contact') {
      const getter = CONTACT_PROPS[name]
      if (!getter) {
        push({ kind: 'text', value: match[0] })
        continue
      }
      const v = getter(ctx.contact).trim()
      push(v ? { kind: 'value', value: v } : { kind: 'missing', label: humanize(name) })
    } else if (ns === 'field') {
      const v = fieldText(ctx.fields[name])
      push(v != null ? { kind: 'value', value: v } : { kind: 'missing', label: humanize(name) })
    } else if (ns === 'computed') {
      const v = ctx.computed[name]
      push(
        typeof v === 'number' && Number.isFinite(v)
          ? { kind: 'value', value: formatCurrency(v) }
          : { kind: 'missing', label: humanize(name) },
      )
    } else if (ns === 'ai') {
      const v = ctx.slots[name]
      if (v) push({ kind: 'value', value: v })
      else if (ctx.omitAi) push({ kind: 'text', value: '' })
      else if (ctx.slotsPending) push({ kind: 'pending' })
      else push({ kind: 'missing', label: humanize(name) })
    } else if (ns === 'caller' && name === 'first_name') {
      const v = ctx.callerFirstName.trim()
      push(v ? { kind: 'value', value: v } : { kind: 'missing', label: 'caller first name' })
    } else {
      push({ kind: 'text', value: match[0] })
    }
  }
  if (cursor < text.length) push({ kind: 'text', value: text.slice(cursor) })
  return segments
}
