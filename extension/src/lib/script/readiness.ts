import type { ContactContext, FieldValue, Question, ScriptDefinition } from '@/lib/api/types'
import { formatCurrency } from '@/lib/time'

export interface RecapRowValue {
  label: string
  value: string | null
  fieldKey?: string
}

export function isEmptyValue(value: FieldValue | undefined): boolean {
  if (value == null) return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'number') return !Number.isFinite(value)
  return value.trim() === ''
}

function toNumber(value: FieldValue | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value.replace(/[$,]/g, ''))
    if (Number.isFinite(n)) return n
  }
  return null
}

export function computeRecap(
  definition: ScriptDefinition,
  context: ContactContext,
): { rows: RecapRowValue[]; computed: Record<string, number | null> } {
  const computed: Record<string, number | null> = {}
  const rows: RecapRowValue[] = []
  for (const section of definition.sections) {
    for (const block of section.blocks) {
      if (block.type !== 'recap') continue
      for (const row of block.rows) {
        if (row.source === 'field') {
          const v = context.fieldValues[row.fieldKey]
          rows.push({
            label: row.label,
            value: isEmptyValue(v) ? null : fieldText(v as FieldValue),
            fieldKey: row.fieldKey,
          })
        } else if (row.source === 'contact') {
          const v =
            row.key === 'company_name'
              ? context.contact.companyName
              : row.key === 'city'
                ? context.contact.city
                : context.contact.postalCode
          rows.push({ label: row.label, value: v.trim() ? v : null })
        } else {
          const [a, b] = row.formula.fields
          const na = toNumber(context.fieldValues[a])
          const nb = toNumber(context.fieldValues[b])
          const product = na != null && nb != null ? na * nb : null
          computed[row.key] = product
          rows.push({ label: row.label, value: product != null ? formatCurrency(product) : null })
        }
      }
    }
  }
  return { rows, computed }
}

function fieldText(value: FieldValue): string {
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

export function allQuestions(definition: ScriptDefinition): Question[] {
  const out: Question[] = []
  for (const section of definition.sections) {
    for (const block of section.blocks) {
      if (block.type === 'question') out.push(block)
    }
  }
  return out
}

export function missingForBooking(
  definition: ScriptDefinition,
  fieldValues: Record<string, FieldValue>,
): { fieldKey: string; label: string }[] {
  return allQuestions(definition)
    .filter((q) => q.requiredForBooking && isEmptyValue(fieldValues[q.fieldKey]))
    .map((q) => ({ fieldKey: q.fieldKey, label: q.label }))
}
