import { describe, expect, it } from 'vitest'
import { renderTemplate, type TemplateCtx } from '@/lib/script/template'
import type { Contact } from '@/lib/api/types'

const contact: Contact = {
  id: 'c_1',
  firstName: 'Maya',
  lastName: 'Reyes',
  companyName: 'Glow Aesthetics Med Spa',
  email: '',
  phone: '+15125550134',
  city: 'Austin',
  state: 'TX',
  postalCode: '',
  website: '',
  tags: [],
}

function ctx(overrides: Partial<TemplateCtx> = {}): TemplateCtx {
  return {
    contact,
    fields: {},
    computed: {},
    slots: {},
    slotsPending: false,
    omitAi: false,
    callerFirstName: 'Sam',
    ...overrides,
  }
}

describe('renderTemplate', () => {
  it('renders contact placeholders as values', () => {
    expect(renderTemplate('Hey {{contact.first_name}} from {{contact.company_name}}', ctx())).toEqual([
      { kind: 'text', value: 'Hey ' },
      { kind: 'value', value: 'Maya' },
      { kind: 'text', value: ' from ' },
      { kind: 'value', value: 'Glow Aesthetics Med Spa' },
    ])
  })

  it('renders missing contact values with readable labels', () => {
    expect(renderTemplate('email {{contact.email}} zip {{contact.postal_code}}', ctx())).toEqual([
      { kind: 'text', value: 'email ' },
      { kind: 'missing', label: 'email' },
      { kind: 'text', value: ' zip ' },
      { kind: 'missing', label: 'postal code' },
    ])
  })

  it('renders field values and joins arrays', () => {
    const c = ctx({
      fields: {
        'contact.monthly_new_patients': 40,
        'contact.procedures_offer': ['botox', 'iv'],
        'contact.their_why': '  ',
      },
    })
    expect(renderTemplate('{{field.contact.monthly_new_patients}}', c)).toEqual([
      { kind: 'value', value: '40' },
    ])
    expect(renderTemplate('{{field.contact.procedures_offer}}', c)).toEqual([
      { kind: 'value', value: 'botox, iv' },
    ])
    expect(renderTemplate('[{{field.contact.their_why}}]', c)).toEqual([
      { kind: 'text', value: '[' },
      { kind: 'missing', label: 'their why' },
      { kind: 'text', value: ']' },
    ])
  })

  it('formats computed values as currency', () => {
    const c = ctx({ computed: { current_revenue: 14000, target_revenue: null } })
    expect(renderTemplate('now {{computed.current_revenue}}', c)).toEqual([
      { kind: 'text', value: 'now ' },
      { kind: 'value', value: '$14,000' },
    ])
    expect(renderTemplate('goal {{computed.target_revenue}}', c)).toEqual([
      { kind: 'text', value: 'goal ' },
      { kind: 'missing', label: 'target revenue' },
    ])
  })

  it('renders ai slots, pending skeletons, and omitted slots', () => {
    expect(renderTemplate('{{ai.opener}}!', ctx({ slots: { opener: 'Hello' } }))).toEqual([
      { kind: 'value', value: 'Hello' },
      { kind: 'text', value: '!' },
    ])
    expect(renderTemplate('{{ai.opener}}!', ctx({ slotsPending: true }))).toEqual([
      { kind: 'pending' },
      { kind: 'text', value: '!' },
    ])
    expect(renderTemplate('A{{ai.opener}}B', ctx({ omitAi: true }))).toEqual([
      { kind: 'text', value: 'AB' },
    ])
  })

  it('renders the caller first name', () => {
    expect(renderTemplate('this is {{caller.first_name}}', ctx())).toEqual([
      { kind: 'text', value: 'this is ' },
      { kind: 'value', value: 'Sam' },
    ])
  })

  it('leaves unknown placeholders and html as literal text', () => {
    expect(renderTemplate('<b>{{foo.bar}}</b>', ctx())).toEqual([
      { kind: 'text', value: '<b>{{foo.bar}}</b>' },
    ])
  })

  it('merges adjacent text and tolerates whitespace', () => {
    expect(renderTemplate('x{{contact.phone}}y', ctx())).toEqual([
      { kind: 'text', value: 'x' },
      { kind: 'value', value: '+15125550134' },
      { kind: 'text', value: 'y' },
    ])
    expect(renderTemplate('{{ contact.city }}', ctx())).toEqual([{ kind: 'value', value: 'Austin' }])
  })
})
