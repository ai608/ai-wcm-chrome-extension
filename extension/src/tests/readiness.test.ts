import { describe, expect, it } from 'vitest'
import { computeRecap, missingForBooking } from '@/lib/script/readiness'
import type { ContactContext, ScriptDefinition } from '@/lib/api/types'

const definition: ScriptDefinition = {
  version: 3,
  sections: [
    {
      id: 'discovery',
      title: 'Discovery',
      defaultOpen: true,
      blocks: [
        { type: 'question', id: 'q1', fieldKey: 'contact.monthly_new_patients', label: 'New patients', input: 'number', requiredForBooking: true },
        { type: 'question', id: 'q2', fieldKey: 'contact.avg_patient_value', label: 'Avg value', input: 'currency', requiredForBooking: true },
        { type: 'question', id: 'q3', fieldKey: 'contact.goal_new_patients', label: 'Goal', input: 'number', requiredForBooking: true },
        { type: 'question', id: 'q4', fieldKey: 'contact.their_why', label: 'Why', input: 'textarea', requiredForBooking: false },
      ],
    },
    {
      id: 'confirm',
      title: 'Confirm',
      defaultOpen: false,
      blocks: [
        {
          type: 'recap',
          id: 'r1',
          rows: [
            { label: 'Clinic', source: 'contact', key: 'company_name' },
            { label: 'New patients / mo', source: 'field', fieldKey: 'contact.monthly_new_patients' },
            { label: 'Why', source: 'field', fieldKey: 'contact.their_why' },
            { label: 'Current revenue', source: 'computed', key: 'current_revenue', formula: { op: 'multiply', fields: ['contact.monthly_new_patients', 'contact.avg_patient_value'] } },
            { label: 'Target revenue', source: 'computed', key: 'target_revenue', formula: { op: 'multiply', fields: ['contact.goal_new_patients', 'contact.avg_patient_value'] } },
          ],
          sayItBack: 'You do {{field.contact.monthly_new_patients}} at {{computed.current_revenue}}.',
        },
      ],
    },
  ],
}

function context(fieldValues: ContactContext['fieldValues']): ContactContext {
  return {
    contact: {
      id: 'c1', firstName: 'M', lastName: 'R', companyName: 'Glow', email: '', phone: '',
      city: 'Austin', state: 'TX', postalCode: '', website: '', tags: [],
    },
    fieldValues,
    enrichment: { status: 'enriched', services: [], googleRating: null, googleReviewCount: null, score: null, updatedAt: null },
  }
}

describe('readiness', () => {
  it('computes recap rows with missing detection', () => {
    const { rows, computed } = computeRecap(
      definition,
      context({ 'contact.monthly_new_patients': 40, 'contact.avg_patient_value': 350 }),
    )
    expect(rows).toEqual([
      { label: 'Clinic', value: 'Glow' },
      { label: 'New patients / mo', value: '40', fieldKey: 'contact.monthly_new_patients' },
      { label: 'Why', value: null, fieldKey: 'contact.their_why' },
      { label: 'Current revenue', value: '$14,000' },
      { label: 'Target revenue', value: null },
    ])
    expect(computed).toEqual({ current_revenue: 14000, target_revenue: null })
  })

  it('finds fields missing for booking', () => {
    expect(
      missingForBooking(definition, { 'contact.monthly_new_patients': 40 }),
    ).toEqual([
      { fieldKey: 'contact.avg_patient_value', label: 'Avg value' },
      { fieldKey: 'contact.goal_new_patients', label: 'Goal' },
    ])
    expect(
      missingForBooking(definition, {
        'contact.monthly_new_patients': 40,
        'contact.avg_patient_value': 350,
        'contact.goal_new_patients': 80,
      }),
    ).toEqual([])
  })
})
