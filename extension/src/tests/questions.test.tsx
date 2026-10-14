import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QuestionField } from '@/components/script/QuestionField'
import type { Block, FieldValue } from '@/lib/api/types'
import { __resetAutosave, useAutosaveStore } from '@/stores/autosave-store'

vi.mock('@/lib/messaging', () => ({
  call: async () => ({ fieldValues: {}, updatedAt: '2026-10-14T00:00:00Z' }),
}))

type Question = Extract<Block, { type: 'question' }>

function question(overrides: Partial<Question> & { input: Question['input'] }): Question {
  return {
    type: 'question',
    id: 'q1',
    fieldKey: 'contact.test_field',
    label: 'Test field',
    requiredForBooking: false,
    ...overrides,
  }
}

function renderField(block: Question, initialValue: FieldValue | undefined = null) {
  return render(<QuestionField contactId="c1" block={block} initialValue={initialValue} />)
}

function queued(): FieldValue | undefined {
  return useAutosaveStore.getState().queue.c1?.['contact.test_field']
}

describe('QuestionField', () => {
  afterEach(() => {
    cleanup()
    __resetAutosave()
  })

  it('commits text input', () => {
    renderField(question({ input: 'text' }))
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: 'hello' } })
    expect(queued()).toBe('hello')
  })

  it('commits textarea input', () => {
    renderField(question({ input: 'textarea' }))
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: 'why now' } })
    expect(queued()).toBe('why now')
  })

  it('commits numbers and rejects invalid input', () => {
    renderField(question({ input: 'number' }))
    const input = screen.getByLabelText('Test field')
    fireEvent.change(input, { target: { value: '42' } })
    expect(queued()).toBe(42)
    fireEvent.change(input, { target: { value: 'abc' } })
    expect(screen.getByText('Enter a number')).toBeDefined()
    expect(queued()).toBe(42)
  })

  it('commits currency as a number', () => {
    renderField(question({ input: 'currency' }))
    fireEvent.change(screen.getByLabelText('Test field'), { target: { value: '350' } })
    expect(queued()).toBe(350)
  })

  it('commits radio choices', () => {
    renderField(
      question({
        input: 'radio',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ],
      }),
    )
    fireEvent.click(screen.getByRole('radio', { name: 'B' }))
    expect(queued()).toBe('b')
  })

  it('toggles checkbox group values', () => {
    const spy = vi.spyOn(useAutosaveStore.getState(), 'setField')
    renderField(
      question({
        input: 'checkbox_group',
        options: [
          { value: 'x', label: 'X' },
          { value: 'y', label: 'Y' },
        ],
      }),
      ['x'],
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'Y' }))
    // happy-dom forwards label clicks to the nested control, toggling twice;
    // the first toggle is the real user intent.
    expect(spy.mock.calls[0]).toEqual(['c1', 'contact.test_field', ['x', 'y'], 'fast'])
    spy.mockRestore()
  })
})
