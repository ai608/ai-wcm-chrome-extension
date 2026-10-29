import * as z from 'zod/mini'
import type { FlowNode } from '@/lib/api/types'

const blockOptionSchema = z.object({ value: z.string(), label: z.string() })

const sayBlockSchema = z.object({
  type: z.literal('say'),
  id: z.string(),
  text: z.string(),
  tone: z.optional(z.union([z.literal('default'), z.literal('highlight')])),
})

const tipBlockSchema = z.object({ type: z.literal('tip'), id: z.string(), text: z.string() })

const responseBlockSchema = z.object({
  type: z.literal('response'),
  id: z.string(),
  label: z.string(),
  text: z.string(),
})

const questionBlockSchema = z.object({
  type: z.literal('question'),
  id: z.string(),
  fieldKey: z.string(),
  label: z.string(),
  help: z.optional(z.string()),
  input: z.union([
    z.literal('text'),
    z.literal('textarea'),
    z.literal('number'),
    z.literal('currency'),
    z.literal('select'),
    z.literal('radio'),
    z.literal('checkbox_group'),
  ]),
  options: z.optional(z.array(blockOptionSchema)),
  requiredForBooking: z.boolean(),
})

const recapRowSchema = z.discriminatedUnion('source', [
  z.object({ label: z.string(), source: z.literal('field'), fieldKey: z.string() }),
  z.object({
    label: z.string(),
    source: z.literal('contact'),
    key: z.union([z.literal('company_name'), z.literal('postal_code'), z.literal('city')]),
  }),
  z.object({
    label: z.string(),
    source: z.literal('computed'),
    key: z.string(),
    formula: z.object({ op: z.literal('multiply'), fields: z.tuple([z.string(), z.string()]) }),
  }),
])

const recapBlockSchema = z.object({
  type: z.literal('recap'),
  id: z.string(),
  rows: z.array(recapRowSchema),
  sayItBack: z.string(),
})

const outcomeSchema = z.object({ id: z.string(), label: z.string(), books: z.boolean() })

const outcomeBlockSchema = z.object({
  type: z.literal('outcome'),
  id: z.string(),
  outcomes: z.array(outcomeSchema),
})

const bookingBlockSchema = z.object({ type: z.literal('booking'), id: z.string() })

const faqBlockSchema = z.object({
  type: z.literal('faq'),
  id: z.string(),
  items: z.array(z.object({ q: z.string(), a: z.string() })),
})

const doNotBookBlockSchema = z.object({
  type: z.literal('do_not_book'),
  id: z.string(),
  items: z.array(z.string()),
})

const blockSchema = z.union([
  sayBlockSchema,
  tipBlockSchema,
  responseBlockSchema,
  questionBlockSchema,
  recapBlockSchema,
  outcomeBlockSchema,
  bookingBlockSchema,
  faqBlockSchema,
  doNotBookBlockSchema,
])

const sectionSchema = z.object({
  id: z.string(),
  title: z.string(),
  defaultOpen: z.boolean(),
  blocks: z.array(blockSchema),
})

const flowNodeSchema: z.ZodMiniType<FlowNode> = z.object({
  ask: z.optional(z.string()),
  options: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      say: z.string(),
      next: z.optional(z.lazy(() => flowNodeSchema)),
    }),
  ),
})

export const scriptDefinitionSchema = z.object({
  version: z.number(),
  sections: z.array(sectionSchema),
  flows: z.optional(z.record(z.string(), flowNodeSchema)),
})

export const configSchema = z.object({
  ghl_location_id: z.string(),
  booking_widget_url: z.string(),
  script_version: z.number(),
})

const fieldValueSchema = z.union([z.string(), z.number(), z.array(z.string()), z.null()])

export const patchFieldsResponseSchema = z.object({
  field_values: z.record(z.string(), fieldValueSchema),
  updated_at: z.string(),
})

const sectionStateSchema = z.union([
  z.literal('pending'),
  z.literal('running'),
  z.literal('ready'),
  z.literal('failed'),
  z.literal('skipped'),
])

export const auditSchema = z.object({
  id: z.string(),
  url: z.string(),
  domain: z.string(),
  status: z.union([
    z.literal('queued'),
    z.literal('running'),
    z.literal('ready'),
    z.literal('partial'),
    z.literal('failed'),
  ]),
  sectionState: z.record(z.string(), sectionStateSchema),
  overview: z.nullable(
    z.optional(z.object({ score: z.nullable(z.number()), grade: z.nullable(z.string()) })),
  ),
})

export const reportSchema = z.object({
  audit: auditSchema,
  preparedFor: z.string(),
  preparedBy: z.string(),
  generatedAt: z.string(),
  intro: z.string(),
})
